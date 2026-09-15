"""Versioned, replayable evaluation of general prompt-only tasks."""
import argparse
import hashlib
import html
import json
import math
import random
import statistics
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from raglab import testgen_api, testgen_cli
from raglab.settings import PROJECT_ROOT
from raglab.testgen_worker import MAX_PAYLOAD, reject_constant

DATASET = PROJECT_ROOT / "data" / "general_eval" / "tasks.jsonl"
VERSION = "general-eval-v1"
SCHEDULE_SEED = 20260915
CLI_PREFIX = (
    "This is a prompt-only evaluation. Do not use tools, read or write files, run commands, "
    "browse, use MCP, or delegate. All needed information is in the prompt. Return only what "
    "the prompt requests as your final answer.\n\n"
)


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def _replay_plan_matches(plan, expected):
    """Accept only verified source refactors for replay; generation stays exact."""
    if plan == expected:
        return True
    compatibility = json.loads((DATASET.parent / "replay_compatibility.json").read_text(
        encoding="utf-8"))
    return any(all(plan.get(key) == value for key, value in entry["previous"].items())
               and {**plan, **entry["current"]} == expected for entry in compatibility)


def _same(left, right):
    """JSON equality with numeric equivalence but booleans kept distinct."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is bool and type(right) is bool and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        try:
            return math.isfinite(left) and math.isfinite(right) and left == right
        except OverflowError:
            return False
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(_same(left[key], right[key]) for key in left)
    return type(left) is type(right) and left == right


def _validate_value(value, depth=0):
    if depth > 8:
        raise ValueError("JSON nesting exceeds 8")
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str) and len(value) > 2000:
            raise ValueError("JSON string exceeds 2000 characters")
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            finite = math.isfinite(value)
        except OverflowError as exc:
            raise ValueError("JSON number is out of range") from exc
        if not finite or abs(value) > 1_000_000_000_000:
            raise ValueError("JSON number must be finite and within +/-1e12")
        return
    if isinstance(value, (list, dict)):
        if len(value) > 100:
            raise ValueError("JSON collection exceeds 100 items")
        children = value if isinstance(value, list) else value.values()
        for child in children:
            _validate_value(child, depth + 1)
        return
    raise ValueError("Unsupported JSON value")


def load_tasks(path=DATASET):
    tasks = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
             if line.strip()]
    if len(tasks) != 60 or len({task.get("id") for task in tasks}) != len(tasks):
        raise ValueError("General pack must contain exactly 60 unique base problems")
    allowed_domains = {"instruction", "reasoning", "transformation", "grounded_factuality"}
    for task in tasks:
        if set(task) != {"id", "domain", "family", "variants", "grader"}:
            raise ValueError(f"Unexpected task fields in {task.get('id')}")
        if task["domain"] not in allowed_domains or not isinstance(task["family"], str):
            raise ValueError(f"Invalid domain/family in {task['id']}")
        variants = task["variants"]
        if not isinstance(variants, dict) or "base" not in variants or len(variants) not in (1, 3):
            raise ValueError(f"Each task needs base, or base plus two variants: {task['id']}")
        if len(variants) == 3 and set(variants) != {"base", "equiv-a", "equiv-b"}:
            raise ValueError(f"Variant IDs are fixed in {task['id']}")
        if any(not isinstance(value, str) or not value.strip() for value in variants.values()):
            raise ValueError(f"Prompts must be nonempty strings in {task['id']}")
        if len(set(variants.values())) != len(variants):
            raise ValueError(f"Prompt variants must be distinct in {task['id']}")
        grader = task["grader"]
        if set(grader) - {"answers", "disposition", "constraints"}:
            raise ValueError(f"Unexpected grader fields in {task['id']}")
        if grader.get("disposition") not in ("answered", "abstained"):
            raise ValueError(f"Invalid reference disposition in {task['id']}")
        answers = grader.get("answers")
        if not isinstance(answers, list) or (grader["disposition"] == "answered" and not answers):
            raise ValueError(f"Answered tasks need accepted answers in {task['id']}")
        if grader["disposition"] == "abstained" and answers:
            raise ValueError(f"Abstention tasks cannot have accepted answers in {task['id']}")
        for item in grader.get("constraints", []):
            if not isinstance(item, dict) or set(item) != {"kind", "value"}:
                raise ValueError(f"Malformed constraint in {task['id']}")
            kind, value = item["kind"], item["value"]
            scalar = {"length": int, "word_count": int, "starts_with": str,
                      "ends_with": str, "type": str}
            if ((kind in scalar and type(value) is not scalar[kind]) or
                    (kind in {"contains_all", "excludes", "keys"} and
                     (not isinstance(value, list) or not all(isinstance(v, str) for v in value))) or
                    (kind in {"lowercase", "uppercase", "sorted", "unique"} and
                     type(value) is not bool) or
                    kind not in set(scalar) | {"contains_all", "excludes", "keys", "lowercase",
                                               "uppercase", "sorted", "unique"}):
                raise ValueError(f"Malformed {kind!r} constraint in {task['id']}")
    if {task["domain"] for task in tasks} != allowed_domains:
        raise ValueError("All four domains must be represented")
    return tasks


def prompt_for(task, variant_id):
    try:
        body = task["variants"][variant_id]
    except KeyError as exc:
        raise ValueError(f"Unknown variant {variant_id!r} for {task['id']}") from exc
    grounding = (" Use only the supplied evidence. If it is insufficient, use disposition "
                 "abstained and answer null." if task["domain"] == "grounded_factuality" else "")
    return (
        body.rstrip() + grounding + "\n\nReturn exactly one JSON object with keys answer and disposition. "
        "Disposition must be answered or abstained. Use null for answer only when abstaining. "
        "Do not add markdown or explanation."
    )


def _constraint_passes(answer, constraint):
    kind, value = constraint["kind"], constraint["value"]
    if kind == "type":
        types = {"string": str, "array": list, "object": dict, "integer": int}
        return value in types and type(answer) is types[value]
    if kind == "length":
        return isinstance(answer, (str, list, dict)) and len(answer) == value
    if kind == "word_count":
        return isinstance(answer, str) and len(answer.split()) == value
    if kind == "starts_with":
        return isinstance(answer, str) and answer.startswith(value)
    if kind == "ends_with":
        return isinstance(answer, str) and answer.endswith(value)
    if kind == "contains_all":
        return isinstance(answer, str) and all(item in answer for item in value)
    if kind == "excludes":
        return isinstance(answer, str) and all(item not in answer for item in value)
    if kind == "lowercase":
        return isinstance(answer, str) and answer == answer.lower()
    if kind == "uppercase":
        return isinstance(answer, str) and answer == answer.upper()
    if kind == "sorted":
        try:
            return isinstance(answer, list) and answer == sorted(answer)
        except TypeError:
            return False
    if kind == "unique":
        return isinstance(answer, list) and len(answer) == len({encoded(item) for item in answer})
    if kind == "keys":
        return isinstance(answer, dict) and set(answer) == set(value)
    raise ValueError(f"Unknown constraint kind: {kind}")


def grade_response(task, raw, generation_error=None):
    constraints = task["grader"].get("constraints", [])
    result = {
        "transport_status": "provider_failure" if generation_error else "completed",
        "disposition": "unknown",
        "format_valid": False,
        "correct": False,
        "constraint_passes": 0,
        "constraint_total": len(constraints),
    }
    if generation_error:
        result["error"] = generation_error
        return result
    try:
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_PAYLOAD:
            raise ValueError("Response must be text within 64 KiB")
        def unique_object(pairs):
            if len({key for key, _ in pairs}) != len(pairs):
                raise ValueError("Duplicate JSON object key")
            return dict(pairs)

        value = json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_object)
        _validate_value(value)
        if type(value) is not dict or set(value) != {"answer", "disposition"}:
            raise ValueError("Response must contain exactly answer and disposition")
        disposition = value["disposition"]
        if disposition not in ("answered", "abstained"):
            raise ValueError("Disposition must be answered or abstained")
        if disposition == "abstained" and value["answer"] is not None:
            raise ValueError("Abstained responses must use null answer")
        if disposition == "answered" and value["answer"] is None:
            raise ValueError("Answered responses must not use null answer")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        result.update(transport_status="completed", error=str(exc))
        return result
    answer = value["answer"]
    passed = sum(_constraint_passes(answer, item) for item in constraints)
    expected_disposition = task["grader"]["disposition"]
    correct = (passed == len(constraints) and disposition == expected_disposition and
               (disposition == "abstained" or
                any(_same(answer, expected) for expected in task["grader"]["answers"])))
    result.update(disposition=disposition, format_valid=True, correct=correct,
                  constraint_passes=passed)
    return result


def validate_dataset(tasks):
    variants = 0
    constraints = 0
    families = set()
    for task in tasks:
        variants += len(task["variants"])
        constraints += len(task["grader"].get("constraints", []))
        families.add((task["domain"], task["family"]))
        grader = task["grader"]
        fixture = {"answer": None, "disposition": "abstained"}
        if grader["disposition"] == "answered":
            fixture = {"answer": grader["answers"][0], "disposition": "answered"}
        result = grade_response(task, encoded(fixture))
        if not result["correct"] or result["constraint_passes"] != result["constraint_total"]:
            raise ValueError(f"Reference answer fails its grader: {task['id']}: {result}")
    return {"base_problems": len(tasks), "prompt_variants": variants,
            "families": len(families), "constraints": constraints,
            "dataset_sha256": digest(tasks)}


def logical_key(system, base_id, variant_id, sample):
    return {"system": system, "base_id": base_id, "variant_id": variant_id,
            "condition": "baseline" if variant_id == "base" else "equivalent",
            "sample": sample}


def make_plan(tasks, system, samples=3, seed=SCHEDULE_SEED, api_config=None, cli_config=None,
              item_ids=None):
    if type(samples) is not int or samples <= 0:
        raise ValueError("Samples must be a positive integer")
    if bool(api_config) == bool(cli_config):
        raise ValueError("Choose exactly one API or CLI transport")
    selected = tasks if item_ids is None else [task for task in tasks if task["id"] in item_ids]
    if (not selected or (item_ids is not None and
                         ({task["id"] for task in selected} != set(item_ids) or
                          len(item_ids) != len(set(item_ids))))):
        raise ValueError("--items must contain known unique base IDs")
    adapter_files = [Path(testgen_api.__file__)] if api_config else [Path(testgen_cli.__file__)]
    adapter_hash = digest([path.read_text(encoding="utf-8") for path in adapter_files])
    system_id = digest({"source": "api" if api_config else "cli", "model": system,
                        "config": api_config or cli_config, "adapter_sha256": adapter_hash})
    schedule = [logical_key(system_id, task["id"], variant_id, sample)
                for task in selected for variant_id in task["variants"]
                for sample in range(1, samples + 1)]
    random.Random(seed).shuffle(schedule)
    return {
        "version": VERSION,
        "dataset_sha256": digest(tasks),
        "system": system,
        "system_id": system_id,
        "item_ids": [task["id"] for task in selected],
        "samples": samples,
        "schedule_seed": seed,
        "schedule": schedule,
        "logical_keys_sha256": digest(sorted(schedule, key=encoded)),
        "prompts_sha256": digest([prompt_for(task, variant)
                                  for task in selected for variant in task["variants"]]),
        "scoring_sha256": digest(Path(__file__).read_text(encoding="utf-8")),
        "adapter_sha256": adapter_hash,
        "api_config": api_config,
        "cli_config": cli_config,
        "policy": "One attempt per frozen logical key; no retries, replacement, or tuning.",
    }


def _task_map(tasks):
    return {task["id"]: task for task in tasks}


def fixture_records(tasks, plan):
    task_by_id = _task_map(tasks)
    plan_hash = digest(plan)
    records = []
    for key in plan["schedule"]:
        task = task_by_id[key["base_id"]]
        grader = task["grader"]
        value = {"answer": None, "disposition": "abstained"}
        if grader["disposition"] == "answered":
            value = {"answer": grader["answers"][0], "disposition": "answered"}
        prompt = prompt_for(task, key["variant_id"])
        records.append({"version": VERSION, "dataset_sha256": digest(tasks), **key,
                        "prompt": prompt, "prompt_sha256": digest(prompt), "source": "fixture",
                        "raw": encoded(value), "plan_sha256": plan_hash,
                        "request_sent": False, "execution_status": "completed",
                        "latency_seconds": None})
    return records


def _execute_request(record, stopped, api_config, cli_config, cli_executable, model, prompt, key,
                     blocked_message=None):
    if api_config:
        record.update(api_config=api_config,
                      request=testgen_api.request_for(api_config, model, prompt))
    else:
        record.update(cli_config=cli_config,
                      cli_prompt=testgen_cli.cli_prompt(prompt, CLI_PREFIX))
    started = time.perf_counter()
    try:
        if stopped:
            record.update(raw="", generation_error=stopped, request_sent=False,
                          execution_status="skipped_after_block")
        elif api_config:
            record.update(testgen_api.generate_one(
                api_config, record["request"], key))
            record["request_sent"] = True
        else:
            record.update(testgen_cli.generate_one(
                cli_config, cli_executable, model, prompt, CLI_PREFIX))
            record["request_sent"] = True
        record.setdefault("execution_status", "provider_error"
                          if record.get("generation_error") else "completed")
        if record.get("http_status") in (401, 403, 429):
            stopped = blocked_message or (
                f"Skipped after HTTP {record['http_status']}; no retry was made")
        if record.get("blocked_reason"):
            stopped = blocked_message or (
                "Skipped after " + record["blocked_reason"] + "; no retry was made")
    except (OSError, ValueError, KeyError) as exc:
        record.update(raw="", generation_error=str(exc), request_sent=False,
                      execution_status="harness_error")
        stopped = "Skipped after transport failure; no retry was made"
    record["latency_seconds"] = (None if record.get("request_sent") is False else
                                 round(time.perf_counter() - started, 3))
    return stopped


def generate(tasks, plan, output, api_config=None, cli_config=None, cli_executable=None):
    expected = make_plan(tasks, plan["system"], plan["samples"], plan["schedule_seed"],
                         api_config, cli_config, plan["item_ids"])
    if plan != expected:
        raise ValueError("Frozen plan differs from current dataset, code, adapter, or configuration")
    key = testgen_api.api_key(api_config) if api_config else None
    task_by_id = _task_map(tasks)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    stopped = None
    with output.open("x", encoding="utf-8") as handle:
        for logical in plan["schedule"]:
            task = task_by_id[logical["base_id"]]
            prompt = prompt_for(task, logical["variant_id"])
            record = {"version": VERSION, "dataset_sha256": digest(tasks), **logical,
                      "prompt": prompt, "prompt_sha256": digest(prompt),
                      "source": "api" if api_config else "cli", "plan_sha256": digest(plan),
                      "requested_at": datetime.now(UTC).isoformat()}
            record["options"] = api_config["options"] if api_config else cli_config
            stopped = _execute_request(record, stopped, api_config, cli_config, cli_executable,
                                       plan["system"], prompt, key)
            handle.write(encoded(record) + "\n")
            handle.flush()
            print(f"{logical['base_id']} / {logical['variant_id']} / {logical['sample']}"
                  + (f" - {record['generation_error']}" if record.get("generation_error") else ""),
                  flush=True)
def validate_model_identity(records):
    """Reject mixed returned identities without modifying the saved raw evidence."""
    returned = {row.get("returned_model") for row in records if row.get("returned_model")}
    if len(returned) > 1:
        raise ValueError("Returned model identity changed; raw evidence remains unchanged")


def validate_execution_status(record, allow_missing=False):
    execution_status = record.get("execution_status")
    if execution_status is None and allow_missing:
        execution_status = "completed" if not record.get("generation_error") else "provider_error"
    if execution_status not in {"completed", "provider_error", "skipped_after_block",
                                "harness_error"}:
        raise ValueError("Unknown execution status")
    has_error = bool(record.get("generation_error"))
    if (execution_status == "completed") == has_error:
        raise ValueError("Execution status and generation error disagree")
    if execution_status in {"skipped_after_block", "harness_error"} and record.get(
            "request_sent") is not False:
        raise ValueError("Skipped and harness-error records must have request_sent false")
    if execution_status == "provider_error" and record.get("request_sent") is not True:
        raise ValueError("Provider errors must follow a sent request")
    if execution_status == "completed" and record.get("source") in {"api", "cli"} and record.get(
            "request_sent") is not True:
        raise ValueError("Completed live records must follow a sent request")
    return execution_status


def _check_record(record, task, plan):
    prompt = prompt_for(task, record["variant_id"])
    if record.get("version") != VERSION or record.get("dataset_sha256") != plan["dataset_sha256"]:
        raise ValueError("Record protocol or dataset provenance differs from plan")
    if record.get("prompt") != prompt or record.get("prompt_sha256") != digest(prompt):
        raise ValueError("Record prompt provenance differs from dataset")
    if record.get("plan_sha256") != digest(plan):
        raise ValueError("Record plan provenance differs from supplied plan")
    if record.get("condition") != ("baseline" if record["variant_id"] == "base"
                                    else "equivalent"):
        raise ValueError("Unknown record condition")
    if record.get("source") == "api":
        config = plan["api_config"]
        if record.get("api_config") != config or record.get("request") != testgen_api.request_for(
                config, plan["system"], prompt):
            raise ValueError("API request provenance differs from plan")
    elif record.get("source") == "cli":
        if (record.get("cli_config") != plan["cli_config"] or
                record.get("cli_prompt") != testgen_cli.cli_prompt(prompt, CLI_PREFIX)):
            raise ValueError("CLI prompt provenance differs from plan")
    elif record.get("source") != "fixture":
        raise ValueError("Unknown record source")


def evaluate(tasks, records, plan):
    if plan["dataset_sha256"] != digest(tasks) or plan["version"] != VERSION:
        raise ValueError("Plan does not match this dataset or protocol")
    expected_plan = make_plan(tasks, plan["system"], plan["samples"], plan["schedule_seed"],
                              plan.get("api_config"), plan.get("cli_config"), plan["item_ids"])
    if not _replay_plan_matches(plan, expected_plan):
        raise ValueError("Plan differs from current dataset, code, adapter, or configuration")
    task_by_id = _task_map(tasks)
    expected_keys = {encoded(key) for key in plan["schedule"]}
    seen = set()
    rows = []
    sources = {record.get("source") for record in records}
    if len(sources) != 1:
        raise ValueError("A run cannot mix fixture, API, and CLI sources")
    validate_model_identity(records)
    for record in records:
        key = logical_key(record.get("system"), record.get("base_id"),
                          record.get("variant_id"), record.get("sample"))
        key_text = encoded(key)
        if key_text in seen:
            raise ValueError("Duplicate logical record key")
        if key_text not in expected_keys or record.get("base_id") not in task_by_id:
            raise ValueError("Unexpected logical record key")
        seen.add(key_text)
        task = task_by_id[record["base_id"]]
        _check_record(record, task, plan)
        execution_status = validate_execution_status(record, allow_missing=True)
        grade = grade_response(task, record.get("raw", ""), record.get("generation_error"))
        grade["transport_status"] = execution_status
        rows.append({**key, "domain": task["domain"], "family": task["family"],
                     "prompt": record["prompt"], "reference": task["grader"],
                     "raw": record.get("raw", ""), "generation_error": record.get(
                         "generation_error"), "latency_seconds": record.get("latency_seconds"),
                     "execution_status": execution_status, **grade})
    missing = expected_keys - seen
    if missing:
        raise ValueError(f"Run is incomplete: {len(missing)} frozen logical keys are missing")
    selected_tasks = [task for task in tasks if task["id"] in plan["item_ids"]]
    return _build_report(selected_tasks, rows, plan, records[0].get("source") if records else None)


def _summary(rows, base_count, variant_count, family_count):
    answered = sum(row["disposition"] == "answered" for row in rows)
    correct = sum(row["correct"] for row in rows)
    attempted_correct = sum(row["correct"] and row["disposition"] == "answered" for row in rows)
    attempted_reference = [row for row in rows if row["disposition"] == "answered"]
    incomplete = any(row["execution_status"] in {"skipped_after_block", "harness_error"}
                     for row in rows)
    baseline_rows = [row for row in rows if row["variant_id"] == "base"]
    per_base = defaultdict(list)
    for row in baseline_rows:
        per_base[row["base_id"]].append(row["correct"])
    return {
        "base_problems": base_count,
        "families": family_count,
        "prompt_variants": variant_count,
        "trials": len(rows),
        "correct": correct,
        "all_variant_trial_success_rate": (round(correct / len(rows), 4)
                                           if rows and not incomplete else None),
        "baseline_macro_success": (round(statistics.mean(
            statistics.mean(values) for values in per_base.values()), 4)
            if per_base and not incomplete else None),
        "run_complete": not incomplete,
        "provider_failures": sum(row["execution_status"] == "provider_error" for row in rows),
        "skipped_after_block": sum(row["execution_status"] == "skipped_after_block" for row in rows),
        "harness_errors": sum(row["execution_status"] == "harness_error" for row in rows),
        "invalid_responses": sum(row["transport_status"] == "completed" and
                                 not row["format_valid"] for row in rows),
        "answered": answered,
        "abstained": sum(row["disposition"] == "abstained" for row in rows),
        "unknown_disposition": sum(row["disposition"] == "unknown" for row in rows),
        "coverage": round(answered / len(rows), 4) if rows and not incomplete else None,
        "attempted_accuracy": round(attempted_correct / len(attempted_reference), 4)
        if attempted_reference and not incomplete else None,
        "constraint_passes": sum(row["constraint_passes"] for row in rows),
        "constraint_total": sum(row["constraint_total"] for row in rows),
    }


def _build_report(tasks, rows, plan, source):
    task_by_id = _task_map(tasks)
    complete = not any(row["execution_status"] in {"skipped_after_block", "harness_error"}
                       for row in rows)
    by_domain = {}
    for domain in sorted({task["domain"] for task in tasks}):
        domain_tasks = [task for task in tasks if task["domain"] == domain]
        domain_rows = [row for row in rows if row["domain"] == domain]
        by_domain[domain] = _summary(
            domain_rows, len(domain_tasks), sum(len(task["variants"]) for task in domain_tasks),
            len({task["family"] for task in domain_tasks}))
    repeated = []
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["base_id"], row["variant_id"])].append(row)
    for (base_id, variant_id), trials in sorted(grouped.items()):
        successes = sum(row["correct"] for row in trials)
        n = len(trials)
        pass_pow_n, pass_at_n = pass_metrics(n, successes, n)
        repeated.append({"base_id": base_id, "domain": task_by_id[base_id]["domain"],
                         "variant_id": variant_id, "samples": len(trials),
                         "successes": successes,
                         "success_rate": round(successes / len(trials), 4) if complete else None,
                         "pass_pow_n": pass_pow_n if complete else None,
                         "pass_at_n": pass_at_n if complete else None})
    robustness = []
    for task in tasks:
        if len(task["variants"]) == 1:
            continue
        baseline = statistics.mean(row["correct"] for row in grouped[(task["id"], "base")])
        for variant_id in ("equiv-a", "equiv-b"):
            variant = statistics.mean(row["correct"]
                                      for row in grouped[(task["id"], variant_id)])
            robustness.append({"base_id": task["id"], "domain": task["domain"],
                               "variant_id": variant_id, "base_success": baseline,
                               "variant_success": variant,
                               "delta": round(variant - baseline, 4)})
    if not complete:
        for item in robustness:
            item.update(base_success=None, variant_success=None, delta=None)
    deltas = [item["delta"] for item in robustness if item["delta"] is not None]
    aggregate_robustness = {
        "paired_base_items": len({item["base_id"] for item in robustness}),
        "paired_comparisons": len(robustness),
        "mean_variant_minus_base": (round(statistics.mean(deltas), 4)
                                    if deltas and complete else None),
        "variant_wins": sum(value > 0 for value in deltas) if complete else None,
        "ties": sum(value == 0 for value in deltas) if complete else None,
        "base_wins": sum(value < 0 for value in deltas) if complete else None,
        "uncertainty": "Descriptive paired base-item effects; no confidence interval is claimed.",
    }
    return {
        "kind": "general_llm_evaluation",
        "version": VERSION,
        "dataset_sha256": digest(tasks),
        "plan_sha256": digest(plan),
        "system": plan["system"],
        "source": source,
        "fixture_notice": "Reference fixture: no model calls were made." if source == "fixture" else None,
        "scope": {"base_problems": len(tasks),
                  "prompt_variants": sum(len(task["variants"]) for task in tasks),
                  "samples": plan["samples"], "trials": len(rows)},
        "summary": _summary(rows, len(tasks), sum(len(task["variants"]) for task in tasks),
                            len({(task["domain"], task["family"]) for task in tasks})),
        "domains": by_domain,
        "repeated_success": repeated,
        "paired_robustness": {"summary": aggregate_robustness, "items": robustness},
        "rows": rows,
        "limitations": [
            "Curated local diagnostic pack; it is not a replication of IFBench, LiveBench, or REFLECT.",
            "Reference labels were code-audited locally, not human-validated.",
            "Repeated trials do not add independent problem diversity.",
            "No aggregate intelligence score or population-level confidence interval is reported.",
        ],
    }


def pass_metrics(n, correct, k):
    """Reliability (all k pass) and retry opportunity (at least one of k passes)."""
    if any(type(value) is not int for value in (n, correct, k)) or not 0 <= correct <= n or not 1 <= k <= n:
        raise ValueError("Pass metrics require integers with 0 <= correct <= n and 1 <= k <= n")
    total = math.comb(n, k)
    pass_pow_k = math.comb(correct, k) / total if correct >= k else 0.0
    pass_at_k = 1 - (math.comb(n - correct, k) / total if n - correct >= k else 0.0)
    return round(pass_pow_k, 4), round(pass_at_k, 4)


def render_html(report):
    esc = lambda value: html.escape(str(value), quote=True)
    rate = lambda value: "unavailable" if value is None else f"{value:.1%}"
    domain_rows = "".join(
        "<tr>" + "".join(f"<td>{esc(value)}</td>" for value in (
            domain, item["base_problems"], item["prompt_variants"], item["trials"],
            item["correct"], rate(item["baseline_macro_success"]), item["provider_failures"],
            item["invalid_responses"], item["answered"], item["abstained"])) + "</tr>"
        for domain, item in report["domains"].items())
    repeated_rows = "".join(
        f"<tr><td>{esc(row['base_id'])}</td><td>{esc(row['variant_id'])}</td>"
        f"<td>{row['successes']}/{row['samples']}</td><td>{rate(row['pass_pow_n'])}</td>"
        f"<td>{rate(row['pass_at_n'])}</td></tr>" for row in report["repeated_success"])
    evidence = "".join(
        f"<tr><td>{esc(row['base_id'])}</td><td>{esc(row['variant_id'])}</td>"
        f"<td>{row['sample']}</td><td>{esc(row['disposition'])}</td>"
        f"<td>{'pass' if row['correct'] else 'fail'}</td><td><pre>{esc(row['prompt'])}</pre></td>"
        f"<td><pre>{esc(json.dumps(row['reference'], ensure_ascii=False, indent=2))}</pre></td>"
        f"<td><pre>{esc(row['raw'])}</pre></td><td>{esc(row.get('error') or row.get('generation_error') or '')}</td></tr>"
        for row in report["rows"])
    limitations = "".join(f"<li>{esc(item)}</li>" for item in report["limitations"])
    robust = report["paired_robustness"]["summary"]
    all_pass = sum(row["pass_pow_n"] == 1 for row in report["repeated_success"])
    robust_delta = ("unavailable" if robust["mean_variant_minus_base"] is None else
                    f"{robust['mean_variant_minus_base'] * 100:+.1f} percentage points")
    return f"""<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>General LLM evaluation</title>
<style>body{{font:16px system-ui;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#172033}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{border:1px solid #ccd3df;padding:.55rem;text-align:left;vertical-align:top}}
th{{background:#eef2f8}}pre{{white-space:pre-wrap;max-width:48rem;margin:0}}code{{overflow-wrap:anywhere}}
.cards{{display:flex;gap:1rem;flex-wrap:wrap}}.card{{padding:1rem;background:#f5f7fb;border-radius:.5rem}}</style>
<main><h1>General LLM evaluation</h1>{f"<p><strong>{esc(report['fixture_notice'])}</strong></p>" if report['fixture_notice'] else ""}<p><strong>{esc(report['system'])}</strong> · {report['scope']['base_problems']} base problems ·
{report['scope']['prompt_variants']} prompt variants · {report['scope']['trials']} trials</p>
<div class=\"cards\"><div class=\"card\">Run status <strong>{'complete' if report['summary']['run_complete'] else 'incomplete'}</strong><br>Skipped: {report['summary']['skipped_after_block']} · harness errors: {report['summary']['harness_errors']}</div><div class=\"card\">Baseline macro success <strong>{rate(report['summary']['baseline_macro_success'])}</strong></div>
<div class=\"card\">Provider failures <strong>{report['summary']['provider_failures']}</strong></div>
<div class=\"card\">Invalid responses <strong>{report['summary']['invalid_responses']}</strong></div></div>
<h2>Domain results</h2><table><thead><tr><th>Domain</th><th>Problems</th><th>Variants</th><th>Trials</th><th>Correct trials</th><th>Baseline macro</th><th>Provider failures</th><th>Invalid</th><th>Answered</th><th>Abstained</th></tr></thead><tbody>{domain_rows}</tbody></table>
<h2>Repeated success</h2><p>{all_pass}/{len(report['repeated_success'])} problem-variant cells passed every repeated attempt. <code>pass^n</code> requires every repeated attempt to pass; <code>pass@n</code> describes retry opportunity.</p><details><summary>Inspect repeated-success cells</summary><table><thead><tr><th>Problem</th><th>Variant</th><th>Successes</th><th>pass^n</th><th>pass@n</th></tr></thead><tbody>{repeated_rows}</tbody></table></details>
<h2>Prompt robustness</h2><p>{robust['paired_comparisons']} paired variant comparisons across {robust['paired_base_items']} base problems. Mean variant-minus-base: <strong>{robust_delta}</strong>. Variant wins: {robust['variant_wins']}; ties: {robust['ties']}; base wins: {robust['base_wins']}.</p><p>{esc(robust['uncertainty'])}</p>
<h2>Limits</h2><ul>{limitations}</ul><details><summary>Inspect raw evidence</summary><table><thead><tr><th>Problem</th><th>Variant</th><th>Sample</th><th>Disposition</th><th>Result</th><th>Prompt</th><th>Reference grader</th><th>Raw response</th><th>Error</th></tr></thead><tbody>{evidence}</tbody></table></details>
<footer><p>Dataset <code>{esc(report['dataset_sha256'])}</code><br>Plan <code>{esc(report['plan_sha256'])}</code></p></footer></main></html>"""


def write_report(report, path):
    path = Path(path)
    if path.suffix != ".json":
        raise ValueError("Report output must end in .json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")


def print_report(report):
    rate = lambda value: "unavailable" if value is None else f"{value:.1%}"
    summary = report["summary"]
    print("General LLM evaluation")
    print(f"Model: {report['system']}")
    print(f"Source: {report['source']}")
    if report["fixture_notice"]:
        print(report["fixture_notice"])
    print("Scope: "
          f"{report['scope']['base_problems']} base problems, "
          f"{report['scope']['prompt_variants']} prompt variants, "
          f"{report['scope']['samples']} samples, {report['scope']['trials']} trials")
    print(f"Status: {'complete' if summary['run_complete'] else 'incomplete'}")
    print("Metrics: "
          f"baseline macro success {rate(summary['baseline_macro_success'])}; "
          f"all-variant trial success {rate(summary['all_variant_trial_success_rate'])}; "
          f"coverage {rate(summary['coverage'])}; attempted accuracy "
          f"{rate(summary['attempted_accuracy'])}")
    print("Domains:")
    robustness = report["paired_robustness"]["items"]
    for domain, item in report["domains"].items():
        cells = [row for row in report["repeated_success"] if row["domain"] == domain]
        all_pass = (sum(row["pass_pow_n"] == 1 for row in cells)
                    if all(row["pass_pow_n"] is not None for row in cells) else None)
        deltas = [row["delta"] for row in robustness
                  if row["domain"] == domain and row["delta"] is not None]
        robust = f"{statistics.mean(deltas) * 100:+.1f} percentage points" if deltas else "unavailable"
        reliability = (f"{all_pass}/{len(cells)} prompts passed every sample"
                       if all_pass is not None else "unavailable")
        print(f"  {domain}: trial success {rate(item['all_variant_trial_success_rate'])}; "
              f"baseline macro {rate(item['baseline_macro_success'])}; reliability "
              f"{reliability}; mean variant-minus-base {robust}")
    print("Failures: "
          f"provider {summary['provider_failures']}; invalid responses "
          f"{summary['invalid_responses']}; skipped {summary['skipped_after_block']}; "
          f"harness {summary['harness_errors']}")
    failed = [row for row in report["rows"] if not row["correct"]]
    if failed:
        print("Failed items:")
        for row in failed:
            detail = (row.get("error") or row.get("generation_error") or
                      "answer or constraints did not match")
            print(f"  {row['base_id']} / {row['variant_id']} / sample {row['sample']}: "
                  f"{row['execution_status']} ({detail})")
    else:
        print("Failed items: none")
    print("Limitations:")
    for limitation in report["limitations"]:
        print(f"  - {limitation}")


def _read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def transport_configuration(args):
    if args.transport == "api":
        options = json.loads(args.options)
        return testgen_api.configuration(args.provider, args.base_url, args.api_key_env, options), None
    return None, testgen_cli.configuration(args.provider, args.cli_version, args.effort)


def add_transport_arguments(parser):
    parser.add_argument("--transport", choices=("api", "cli"), required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-env")
    parser.add_argument("--options", default="{}")
    parser.add_argument("--cli-version", default="unknown")
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--output", type=Path, required=True)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate")
    for name in ("freeze", "generate"):
        item = commands.add_parser(name)
        add_transport_arguments(item)
        item.add_argument("--samples", type=int, default=3 if name == "freeze" else None)
        item.add_argument("--items", help="Comma-separated diagnostic subset; default is all 60")
        if name == "generate":
            item.add_argument("--plan", type=Path, required=True)
            item.add_argument("--cli-executable")
    evaluate_parser = commands.add_parser("evaluate")
    evaluate_parser.add_argument("--plan", type=Path, required=True)
    evaluate_parser.add_argument("--generations", type=Path, required=True)
    evaluate_parser.add_argument("--output", type=Path,
                                 help="Optional JSON report path")
    demo = commands.add_parser("demo")
    demo.add_argument("--directory", type=Path,
                      help="Optional directory for fixture JSON artifacts")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    tasks = load_tasks()
    if args.command == "validate":
        print(json.dumps(validate_dataset(tasks), indent=2))
        return
    if args.command in ("freeze", "generate"):
        api_config, cli_config = transport_configuration(args)
        if args.command == "freeze":
            item_ids = args.items.split(",") if args.items else None
            plan = make_plan(tasks, args.model, args.samples, api_config=api_config,
                             cli_config=cli_config, item_ids=item_ids)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(plan, indent=2, allow_nan=False) + "\n")
            print(f"Frozen {len(plan['schedule'])} logical calls in {args.output}")
        else:
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            if args.model != plan["system"] or (args.samples is not None and
                                                args.samples != plan["samples"]):
                raise ValueError("Generation model or samples differ from the frozen plan")
            if args.items and args.items.split(",") != plan["item_ids"]:
                raise ValueError("Generation items differ from the frozen plan")
            generate(tasks, plan, args.output, api_config, cli_config, args.cli_executable)
        return
    if args.command == "evaluate":
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        report = evaluate(tasks, _read_jsonl(args.generations), plan)
        print_report(report)
        if args.output:
            write_report(report, args.output)
            print(f"JSON report: {args.output}")
        return
    plan = make_plan(tasks, "reference-fixture", samples=3,
                     cli_config=testgen_cli.configuration("codex", "fixture"))
    records = fixture_records(tasks, plan)
    report = evaluate(tasks, records, plan)
    print_report(report)
    if args.directory:
        args.directory.mkdir(parents=True, exist_ok=True)
        plan_path = args.directory / "fixture-plan.json"
        raw_path = args.directory / "fixture-generations.jsonl"
        report_path = args.directory / "fixture-report.json"
        plan_path.write_text(json.dumps(plan, indent=2, allow_nan=False) + "\n",
                             encoding="utf-8")
        raw_path.write_text("".join(encoded(row) + "\n" for row in records), encoding="utf-8")
        write_report(report, report_path)
        print(f"Fixture artifacts: {args.directory}")


if __name__ == "__main__":
    main()
