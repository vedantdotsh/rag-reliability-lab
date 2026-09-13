"""Paired, data-only LLM test-generation benchmark using the local Ollama API."""
import argparse
import ast
import copy
import hashlib
import json
import os
import random
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib import error, request

from raglab.settings import PROJECT_ROOT
from raglab.testgen_view import render_html
from raglab.testgen_worker import MAX_PAYLOAD, reject_constant, validate_tests

DATASET = PROJECT_ROOT / "data" / "testgen" / "tasks.jsonl"
CONDITIONS = ("code_only", "code_docs")
VERSION = "testgen-v4"
# ponytail: one seeded sample per condition; use repeated seeds for confidence intervals.
OPTIONS = {"temperature": 0, "seed": 42, "num_predict": 1536, "num_ctx": 4096}
LEGACY_SCHEMA = {
    "type": "object",
    "properties": {"tests": {
        "type": "array", "minItems": 4, "maxItems": 4,
        "items": {"oneOf": [
            {"type": "object", "properties": {
                "args": {"type": "array", "items": {}, "maxItems": 6}, "expected": {}},
             "required": ["args", "expected"], "additionalProperties": False},
            {"type": "object", "properties": {
                "args": {"type": "array", "items": {}, "maxItems": 6},
                "raises": {"type": "string", "enum": [
                    "ValueError", "TypeError", "KeyError", "IndexError", "ZeroDivisionError"]}},
             "required": ["args", "raises"], "additionalProperties": False},
        ]},
    }},
    "required": ["tests"], "additionalProperties": False,
}


def schema_for(task, version=VERSION):
    if version == "testgen-v1":
        return "json"
    if version == "testgen-v2":
        return LEGACY_SCHEMA
    if version not in ("testgen-v3", VERSION):
        raise ValueError("Unknown benchmark protocol")
    # Empty schemas map to objects in the local grammar backend: enumerate JSON types.
    value = {"type": ["string", "number", "boolean", "null", "array", "object"],
             "items": {"$ref": "#/$defs/value"},
             "additionalProperties": {"$ref": "#/$defs/value"}}
    schema = copy.deepcopy(LEGACY_SCHEMA)
    schema["$defs"] = {"value": value}
    function = next(node for node in ast.parse(task["code"]).body
                    if isinstance(node, ast.FunctionDef) and node.name == "target")
    arity = len(function.args.posonlyargs) + len(function.args.args)
    for variant in schema["properties"]["tests"]["items"]["oneOf"]:
        variant["properties"]["args"].update(
            minItems=arity, maxItems=arity, items={"$ref": "#/$defs/value"})
        if "expected" in variant["properties"]:
            variant["properties"]["expected"] = {"$ref": "#/$defs/value"}
    return schema


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def inference_settings(model):
    if model.split(":")[0] == "qwen3.5":
        return {"think": False, "options": {
            **OPTIONS, "presence_penalty": 0, "repeat_penalty": 1.0}}
    return {"options": OPTIONS}


def load_tasks(path=DATASET):
    tasks = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
             if line.strip()]
    if not tasks or len({task["id"] for task in tasks}) != len(tasks):
        raise ValueError("Dataset must contain unique task IDs")
    for task in tasks:
        if task["split"] not in ("dev", "test") or not task["mutants"]:
            raise ValueError("Each task needs a dev/test split and mutants")
        validate_tests(task["reference_tests"])
        codes = [task["code"], *(mutant["code"] for mutant in task["mutants"])]
        if len(set(codes)) != len(codes):
            raise ValueError(f"Duplicate implementation in {task['id']}")
        if len({m["id"] for m in task["mutants"]}) != len(task["mutants"]):
            raise ValueError("Mutant IDs must be unique within a task")
        for code in codes:
            compile(code, task["id"], "exec")
    return tasks


def prompt_for(task, condition, version=VERSION):
    if condition not in CONDITIONS:
        raise ValueError("Unknown prompt condition")
    prompt = (
        "Create boundary-focused tests for the Python function below. Return ONLY a JSON "
        "object with a tests array. Each case must have args (positional arguments) and "
        "exactly one of expected (a JSON return value) or raises (an exception name). "
        "No Python code, markdown, or explanations. Use 1 to 12 tests, at most 6 arguments "
        "per test, arrays/objects at most 100 items, strings at most 2000 characters, "
        "nesting at most 8, finite numbers with magnitude at most 1000000. Allowed "
        "exceptions: ValueError, TypeError, KeyError, IndexError, ZeroDivisionError. "
        "Use exact JSON types: true differs from 1. Test only the specified input domain; "
        "do not invent requirements. Example shape: "
        '{"tests":[{"args":[1],"expected":2},{"args":[-1],"raises":"ValueError"}]}.\n\n'
        "Python function:\n" + task["code"]
    )
    if version in ("testgen-v2", "testgen-v3"):
        prompt = (
            "Write exactly FOUR different tests for this Python function. Read the implementation "
            "literally. For each input, trace the executed statements and compute its exact return "
            "value before writing expected. Do not assume behavior from a common function name. "
            "Use normal inputs plus relevant boundary cases: empty values, equality, ordering, "
            "duplicates or invalid ranges, only when applicable. Use a raises case only when "
            "the code actually raises that exception for those arguments. Do not invent validation "
            "or remove punctuation unless the code does so. Prefer short, simple inputs you can "
            "compute correctly. Follow the function argument count.\n"
            "Return only JSON with tests. Each test contains args and exactly one of expected "
            "or raises. Preserve JSON types (true differs from 1). Arrays/objects have at most "
            "100 items; strings at most 2000 characters; nesting at most 8; finite numbers "
            "within +/-1000000. No explanations or Python test code.\n"
            "Output schema:\n" + encoded(schema_for(task, version))
            + "\n\nPython function:\n" + task["code"]
        )
    elif version == VERSION:
        prompt = (
            "Generate exactly four tests for target below. Follow the implementation exactly, "
            "including its boundary behavior. Compute each expected result by tracing the code. "
            "Cover ordinary behavior and relevant edge cases using small, distinct inputs. "
            "Do not invent validation or exceptions.\n\n"
            "Output JSON only: {\"tests\": [test, test, test, test]}. "
            "Each test has args and exactly one of expected or raises. "
            "The args array contains positional arguments, not the elements of one list argument. "
            "For example, for an UNRELATED function add_offset(values, n) that adds n to every "
            "list element, one test is {\"args\":[[2,5],3],\"expected\":[5,8]}. "
            "For a one-argument list function, passing [2,5] means args:[[2,5]], NOT args:[2,5]. "
            "Return expected values directly, without type/value wrappers. "
            "Use raises only when those exact args actually cause that exception. "
            "Allowed exception names: ValueError, TypeError, KeyError, IndexError, ZeroDivisionError. "
            "JSON booleans differ from integers. Use finite numbers within +/-1000000, strings "
            "at most 2000 characters, collections at most 100 items, nesting at most 8.\n\n"
            "Python function:\n" + task["code"]
        )
    elif version != "testgen-v1":
        raise ValueError("Unknown benchmark protocol")
    if condition == "code_docs":
        prompt += "\nDocumentation:\n" + task["docs"]
    return prompt


def parse_generation(raw):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_PAYLOAD:
        raise ValueError("Model response must be JSON text within 64 KiB")
    value = json.loads(raw, parse_constant=reject_constant)
    if type(value) is not dict or set(value) != {"tests"}:
        raise ValueError("Model response must contain exactly tests")
    return validate_tests(value["tests"])


def run_suite(code, tests, timeout=3):
    validate_tests(tests)
    payload = encoded({"code": code, "tests": tests}).encode("utf-8")
    if len(payload) > MAX_PAYLOAD:
        return {"error": "Execution payload exceeds 64 KiB"}
    worker = Path(__file__).with_name("testgen_worker.py")
    environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR")
                   if key in os.environ}
    try:
        with tempfile.TemporaryDirectory(prefix="testgen-") as directory:
            completed = subprocess.run(
                [sys.executable, "-I", "-S", str(worker)], input=payload,
                capture_output=True, cwd=directory, env=environment, timeout=timeout,
                check=False,
            )
    except subprocess.TimeoutExpired:
        return {"error": "Execution timeout"}
    except OSError as exc:
        return {"error": f"Could not start worker: {exc}"}
    try:
        result = json.loads(completed.stdout)
    except (ValueError, UnicodeError):
        return {"error": f"Worker exited without JSON (exit {completed.returncode})"}
    if completed.returncode and "error" not in result:
        return {"error": f"Worker exited with {completed.returncode}"}
    return result


def all_pass(result):
    return "error" not in result and all(item["passed"] for item in result["outcomes"])


def paired_comparison(deltas):
    # ponytail: task bootstrap describes this dataset, not uncertainty across model generations.
    rng = random.Random(1729)
    samples = [statistics.mean(rng.choices(deltas, k=len(deltas))) for _ in range(2000)]
    quantiles = statistics.quantiles(samples, n=40, method="inclusive")
    return {
        "mean_docs_minus_code": round(statistics.mean(deltas), 4),
        "task_bootstrap_95_ci": [round(quantiles[0], 4), round(quantiles[-1], 4)],
        "docs_wins": sum(value > 0 for value in deltas),
        "ties": sum(value == 0 for value in deltas),
        "code_wins": sum(value < 0 for value in deltas),
        "bootstrap_resamples": 2000, "bootstrap_seed": 1729,
    }


def validate_dataset(tasks):
    for task in tasks:
        result = run_suite(task["code"], task["reference_tests"])
        if not all_pass(result):
            raise ValueError(f"Reference tests fail correct implementation: {task['id']}: {result}")
        for mutant in task["mutants"]:
            result = run_suite(mutant["code"], task["reference_tests"])
            if "error" in result or all_pass(result):
                raise ValueError(f"Reference tests do not kill {task['id']}/{mutant['id']}: {result}")
    return {"tasks": len(tasks), "mutants": sum(len(t["mutants"]) for t in tasks),
            "dataset_sha256": digest(tasks)}


def record_for(task, condition, fingerprint, model, model_digest, source, version=VERSION):
    prompt = prompt_for(task, condition, version)
    return {
        "version": version, "dataset_sha256": fingerprint, "task_id": task["id"],
        "split": task["split"], "condition": condition, "prompt": prompt,
        "prompt_sha256": digest(prompt), "model": model, "model_digest": model_digest,
        **inference_settings(model), "source": source,
        "format": schema_for(task, version),
    }


def api(base_url, endpoint, payload=None):
    data = None if payload is None else encoded(payload).encode("utf-8")
    req = request.Request(base_url.rstrip("/") + endpoint, data=data,
                          headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=240) as response:
        return json.load(response)


def local_model_digest(base_url, model):
    tags = api(base_url, "/api/tags")["models"]
    match = next((tag for tag in tags if tag["name"] == model), None)
    if match is None:
        raise ValueError(f"Local model {model!r} is not installed; use an exact name from ollama list")
    return match["digest"]


def make_plan(tasks, model, model_digest, version=VERSION, runtime_version=None):
    selected = [task for task in tasks if task["split"] == "test"]
    return {
        "version": version, "dataset_sha256": digest(tasks),
        "model": model, "model_digest": model_digest, **inference_settings(model),
        "runtime_version": runtime_version,
        "task_ids": [task["id"] for task in selected],
        "prompts_sha256": digest([prompt_for(task, condition, version)
                                  for task in selected for condition in CONDITIONS]),
        "schemas_sha256": digest([schema_for(task, version) for task in selected]),
        "scoring_sha256": digest([
            Path(__file__).read_text(encoding="utf-8"),
            Path(__file__).with_name("testgen_worker.py").read_text(encoding="utf-8"),
        ]),
        "policy": "One generation per task/condition; no retries or tuning on held-out outputs.",
    }


def generate(tasks, selected, output, model, base_url, version=VERSION, plan=None):
    fingerprint = digest(tasks)
    model_digest = local_model_digest(base_url, model)
    runtime_version = api(base_url, "/api/version").get("version")
    if any(task["split"] == "test" for task in selected):
        if plan is None:
            raise ValueError("Held-out generation requires --plan from the freeze command")
        expected = make_plan(tasks, model, model_digest, version, runtime_version)
        if plan.get("configuration") != expected or [t["id"] for t in selected] != expected["task_ids"]:
            raise ValueError("Frozen plan differs from current configuration or selected tasks")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        for task in selected:
            for condition in CONDITIONS:
                record = record_for(task, condition, fingerprint, model, model_digest,
                                    "ollama", version)
                record["runtime_version"] = runtime_version
                if plan:
                    record["plan_sha256"] = digest(plan)
                started = time.perf_counter()
                try:
                    response = api(base_url, "/api/chat", {
                        "model": model, "stream": False, "format": record["format"],
                        **inference_settings(model),
                        "messages": [{"role": "user", "content": record["prompt"]}],
                    })
                    record.update(raw=response["message"]["content"],
                                  prompt_tokens=response.get("prompt_eval_count"),
                                  prompt_cached_tokens=response.get("prompt_eval_cached_count"),
                                  completion_tokens=response.get("eval_count"),
                                  created_at=response.get("created_at"),
                                  load_duration_ns=response.get("load_duration"),
                                  eval_duration_ns=response.get("eval_duration"),
                                  done_reason=response.get("done_reason"))
                    if not response.get("done") or response.get("done_reason") == "length":
                        record["generation_error"] = "Model response did not finish normally"
                except (error.URLError, TimeoutError, ValueError, KeyError) as exc:
                    record.update(raw="", generation_error=str(exc))
                record["latency_seconds"] = round(time.perf_counter() - started, 3)
                handle.write(encoded(record) + "\n")
                handle.flush()
                print(f"{task['id']} / {condition}: {record['latency_seconds']}s", flush=True)
    final_digest = local_model_digest(base_url, model)
    if final_digest != model_digest:
        records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
        for record in records:
            record["generation_error"] = "Model changed during run; this attempt is invalid"
            record["model_digest_final"] = final_digest
        output.write_text("".join(encoded(record) + "\n" for record in records), encoding="utf-8")
        raise ValueError("Model changed during run; preserved and invalidated the attempt")


def evaluate(tasks, records):
    if not records:
        raise ValueError("No generation records")
    indexed = {task["id"]: task for task in tasks}
    fingerprint = digest(tasks)
    seen = set()
    configurations = set()
    rows = []
    for record in records:
        task = indexed.get(record["task_id"])
        condition = record["condition"]
        key = (record["task_id"], condition)
        if task is None or condition not in CONDITIONS or key in seen:
            raise ValueError("Unknown task/condition or duplicate generation record")
        version = record["version"]
        prompt = prompt_for(task, condition, version)
        expected_format = schema_for(task, version)
        if (record.get("format", "json") != expected_format
                or record["dataset_sha256"] != fingerprint
                or record["split"] != task["split"] or record["prompt"] != prompt
                or record["prompt_sha256"] != digest(prompt)):
            raise ValueError("Generation provenance does not match the dataset/prompt")
        if record["source"] not in ("ollama", "reference_fixture"):
            raise ValueError("Unknown generation source")
        configurations.add(encoded([record["model"], record["model_digest"],
                                       record["options"], record["source"], version,
                                       record.get("plan_sha256"), record.get("think"),
                                       record.get("runtime_version")]))
        seen.add(key)
        row = {"task_id": task["id"], "split": task["split"], "condition": condition,
               "status": "valid", "killed": [], "mutants": len(task["mutants"]),
               "latency_seconds": record.get("latency_seconds"),
               "prompt_tokens": record.get("prompt_tokens"),
               "completion_tokens": record.get("completion_tokens"), "raw": record["raw"]}
        if record.get("generation_error"):
            row.update(status="generation_error", error=record["generation_error"])
            rows.append(row)
            continue
        try:
            tests = parse_generation(record["raw"])
            if record["source"] == "ollama" and version != "testgen-v1" and len(tests) != 4:
                raise ValueError("Structured protocols require exactly four tests")
            if record["source"] == "ollama" and version in ("testgen-v3", VERSION):
                arity = expected_format["properties"]["tests"]["items"]["oneOf"][0][
                    "properties"]["args"]["minItems"]
                if any(len(case["args"]) != arity for case in tests):
                    raise ValueError("Each case must supply the function's positional arguments")
        except (ValueError, RecursionError) as exc:
            row.update(status="invalid_generation", error=str(exc))
        else:
            correct = run_suite(task["code"], tests)
            row.update(test_count=len(tests), tests=tests, correct=correct)
            if "error" in correct:
                row["status"] = "execution_error"
            elif not all_pass(correct):
                row["status"] = "false_alarm"
            else:
                results = {mutant["id"]: run_suite(mutant["code"], tests)
                           for mutant in task["mutants"]}
                row["mutant_results"] = results
                row["killed"] = [name for name, result in results.items()
                                 if "error" not in result and not all_pass(result)]
                if any("error" in result for result in results.values()):
                    row["status"] = "execution_error"
        rows.append(row)
    if len(configurations) != 1:
        raise ValueError("Paired comparison requires one model, digest, options, and source")
    selected_ids = {key[0] for key in seen}
    if seen != {(task_id, condition) for task_id in selected_ids for condition in CONDITIONS}:
        raise ValueError("Every selected task needs both prompt conditions")
    summary = {}
    for condition in CONDITIONS:
        group = [row for row in rows if row["condition"] == condition]
        total = sum(row["mutants"] for row in group)
        killed = sum(len(row["killed"]) for row in group)
        latency = [row["latency_seconds"] for row in group
                   if row["latency_seconds"] is not None]
        summary[condition] = {
            "suites": len(group), "mutants_total": total, "mutants_killed": killed,
            "mutation_score": round(killed / total, 4),
            **{status: sum(row["status"] == status for row in group)
               for status in ("valid", "false_alarm", "invalid_generation",
                              "generation_error", "execution_error")},
            "median_latency_seconds": round(statistics.median(latency), 3) if latency else None,
            **{field: sum(row[field] for row in group) if
               all(row[field] is not None for row in group) else None
               for field in ("prompt_tokens", "completion_tokens")},
        }
    paired = []
    for task_id in sorted(selected_ids):
        scores = {row["condition"]: len(row["killed"]) / row["mutants"]
                  for row in rows if row["task_id"] == task_id}
        paired.append({"task_id": task_id,
                       "docs_minus_code": scores["code_docs"] - scores["code_only"]})
    return {
        "version": records[0]["version"], "dataset_sha256": fingerprint,
        "source": records[0]["source"], "model": records[0]["model"],
        "model_digest": records[0]["model_digest"], "options": records[0]["options"],
        "think": records[0].get("think"),
        "runtime_version": records[0].get("runtime_version"),
        "selected_tasks": sorted(selected_ids), "dataset_tasks": len(tasks),
        "splits": sorted({indexed[task_id]["split"] for task_id in selected_ids}),
        "summary": summary, "paired_deltas": paired, "rows": rows,
        "comparison": paired_comparison([row["docs_minus_code"] for row in paired]),
        "plan_sha256": records[0].get("plan_sha256"),
    }


def write_report(report, path):
    if path.suffix != ".json":
        raise ValueError("Report path must end in .json; .md and .html are written alongside it")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    fixture = report["source"] == "reference_fixture"
    lines = [
        "# LLM test-generation benchmark", "",
        "**REFERENCE FIXTURE — no LLM was used; this checks the runner only.**" if fixture
        else "**Local LLM run — exploratory results, not an estimate of general capability.**",
        "", f"Model: `{report['model']}`",
        (f"Scope: {len(report['selected_tasks'])}/{report['dataset_tasks']} tasks; "
         f"splits: {', '.join(report['splits'])}."),
        f"Dataset SHA-256: `{report['dataset_sha256']}`", "",
        f"Protocol: `{report['version']}`", "",
        ("| Prompt | Bugs caught / total | Score | Valid suites | False alarms | Invalid | "
         "Generation errors | Execution errors | Median generation seconds | Input / output tokens |"),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for condition, item in report["summary"].items():
        lines.append(
            f"| {condition} | {item['mutants_killed']}/{item['mutants_total']} | "
            f"{item['mutation_score']:.1%} | {item['valid']}/{item['suites']} | "
            f"{item['false_alarm']} | {item['invalid_generation']} | "
            f"{item['generation_error']} | {item['execution_error']} | "
            f"{item['median_latency_seconds']} | "
            f"{item['prompt_tokens']} / {item['completion_tokens']} |"
        )
    lines += [
        "", ("A suite earns bug-detection credit only after every assertion passes the correct "
        "implementation. Invalid suites and false alarms earn zero. Execution errors/timeouts "
        "never count as kills; all seeded mutants remain in the denominator."),
        "", ("Small synthetic dataset; one generation per task and condition. Fixed seed is "
        "best-effort. Timings include local load/queue overhead; code-only runs first in each pair. "
        "These results do not establish a statistically reliable prompt advantage."),
        "", (f"Mean paired documentation difference: "
             f"{report['comparison']['mean_docs_minus_code']:+.1%}. "
             f"95% task-bootstrap interval: "
             f"{report['comparison']['task_bootstrap_95_ci'][0]:+.1%} to "
             f"{report['comparison']['task_bootstrap_95_ci'][1]:+.1%}. "
             "This resamples tasks, not repeated model generations."),
        "", "## Paired scores", "", "| Task | Documentation minus code-only score |",
        "|---|---:|",
    ]
    lines.extend(f"| {row['task_id']} | {row['docs_minus_code']:+.1%} |"
                 for row in report["paired_deltas"])
    path.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.with_suffix(".html").write_text(render_html(report), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET,
                        help="Trusted author-written dataset; its Python code will execute")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate", help="Verify references pass and kill every seeded mutant")
    freeze = commands.add_parser("freeze", help="Freeze the complete held-out experiment")
    freeze.add_argument("--model", required=True)
    freeze.add_argument("--base-url", default="http://127.0.0.1:11434")
    freeze.add_argument("--output", type=Path, required=True)
    freeze.add_argument("--protocol", choices=("testgen-v1", "testgen-v2", "testgen-v3", VERSION),
                        default=VERSION)
    demo = commands.add_parser("demo", help="Offline reference-fixture runner check, not LLM results")
    demo.add_argument("--report", type=Path, default=PROJECT_ROOT / "reports/testgen/demo.json")
    gen = commands.add_parser("generate", help="Generate paired JSON tests using an installed model")
    gen.add_argument("--model", required=True)
    gen.add_argument("--base-url", default="http://127.0.0.1:11434")
    gen.add_argument("--split", choices=("dev", "test"), default="dev")
    gen.add_argument("--limit", type=int)
    gen.add_argument("--output", type=Path, required=True)
    gen.add_argument("--protocol", choices=("testgen-v1", "testgen-v2", "testgen-v3", VERSION),
                     default=VERSION)
    gen.add_argument("--plan", type=Path)
    evaluation = commands.add_parser("evaluate", help="Evaluate saved generations without an LLM")
    evaluation.add_argument("--input", type=Path, required=True)
    evaluation.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        tasks = load_tasks(args.dataset)
        if args.command == "validate":
            print(encoded(validate_dataset(tasks)))
        elif args.command == "freeze":
            plan = {"created_at": datetime.now(UTC).isoformat(),
                    "configuration": make_plan(
                        tasks, args.model, local_model_digest(args.base_url, args.model),
                        version=args.protocol,
                        runtime_version=api(args.base_url, "/api/version").get("version"))}
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(plan, indent=2) + "\n")
            print(f"Frozen plan: {args.output} (SHA-256 {digest(plan)})")
        elif args.command == "generate":
            selected = [task for task in tasks if task["split"] == args.split]
            if args.limit is not None and args.limit <= 0:
                raise ValueError("--limit must be positive")
            generate(tasks, selected[:args.limit], args.output, args.model,
                     args.base_url, args.protocol,
                     json.loads(args.plan.read_text(encoding="utf-8")) if args.plan else None)
        else:
            if args.command == "demo":
                records = []
                for task in tasks:
                    for condition in CONDITIONS:
                        record = record_for(task, condition, digest(tasks),
                                            "reference_fixture", None, "reference_fixture")
                        record["raw"] = encoded({"tests": task["reference_tests"]})
                        records.append(record)
            else:
                records = [json.loads(line) for line in args.input.read_text(
                    encoding="utf-8").splitlines() if line.strip()]
            report = evaluate(tasks, records)
            write_report(report, args.report)
            print(encoded(report["summary"]))
            print(f"Report: {args.report.with_suffix('.md')}")
    except (ValueError, KeyError, OSError, RecursionError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
