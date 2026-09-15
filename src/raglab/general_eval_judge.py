"""Fixed grader controls and optional pairwise model-judge evaluation."""
import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from raglab import general_eval, testgen_api, testgen_cli
from raglab.settings import PROJECT_ROOT
from raglab.testgen_worker import MAX_PAYLOAD, reject_constant

CONTROLS = PROJECT_ROOT / "data" / "general_eval" / "grader_controls.jsonl"
VERSION = "general-judge-v1"


def load_controls(path=CONTROLS):
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]
    expected_fields = {"id", "kind", "task_id", "answer_a", "answer_b", "expected", "split"}
    if len(rows) != 12 or len({row.get("id") for row in rows}) != len(rows):
        raise ValueError("Judge control pack must contain 12 unique controls")
    for row in rows:
        if set(row) != expected_fields or row["expected"] not in {"A", "TIE"}:
            raise ValueError(f"Malformed judge control: {row.get('id')}")
        if row["split"] not in {"calibration", "test"} or row["answer_a"] == row["answer_b"]:
            raise ValueError(f"Malformed judge split or answers: {row['id']}")
    return rows


def validate_controls(tasks, controls):
    by_id = {task["id"]: task for task in tasks}
    kinds = set()
    for control in controls:
        if control["task_id"] not in by_id:
            raise ValueError(f"Unknown control task: {control['task_id']}")
        task = by_id[control["task_id"]]
        a = general_eval.grade_response(task, control["answer_a"])
        b = general_eval.grade_response(task, control["answer_b"])
        if not a["correct"] or b["correct"] != (control["expected"] == "TIE"):
            raise ValueError(f"Control labels disagree with objective grader: {control['id']}")
        kinds.add(control["kind"])
    calibration_tasks = {c["task_id"] for c in controls if c["split"] == "calibration"}
    test_tasks = {c["task_id"] for c in controls if c["split"] == "test"}
    if calibration_tasks & test_tasks:
        raise ValueError("Judge calibration and test controls must use disjoint tasks")
    return {"controls": len(controls), "calibration": sum(c["split"] == "calibration"
                                                          for c in controls),
            "test": sum(c["split"] == "test" for c in controls),
            "kinds": sorted(kinds), "controls_sha256": general_eval.digest(controls)}


def judge_prompt(task, control, order):
    first, second = ((control["answer_a"], control["answer_b"])
                     if order == "ab" else (control["answer_b"], control["answer_a"]))
    return (
        "Judge two candidate responses to the task using only the task text. Choose A if only "
        "response A is fully correct, B if only response B is fully correct, or TIE if both are "
        "fully correct. Do not reward style.\n\nTask:\n" + general_eval.prompt_for(task, "base") +
        "\n\nResponse A:\n" + first + "\n\nResponse B:\n" + second +
        '\n\nReturn only JSON: {"winner":"A"}, {"winner":"B"}, or {"winner":"TIE"}.'
    )


def make_plan(tasks, controls, model, api_config=None, cli_config=None):
    if bool(api_config) == bool(cli_config):
        raise ValueError("Choose exactly one API or CLI transport")
    validate_controls(tasks, controls)
    adapter = Path(testgen_api.__file__) if api_config else Path(testgen_cli.__file__)
    adapter_hash = general_eval.digest(adapter.read_text(encoding="utf-8"))
    system_id = general_eval.digest({"source": "api" if api_config else "cli", "model": model,
                                     "config": api_config or cli_config,
                                     "adapter_sha256": adapter_hash})
    schedule = [{"system": system_id, "control_id": control["id"], "order": order,
                 "condition": "pairwise_judge", "sample": 1}
                for control in controls for order in ("ab", "ba")]
    return {"version": VERSION, "model": model, "system_id": system_id,
            "dataset_sha256": general_eval.digest(tasks),
            "controls_sha256": general_eval.digest(controls), "schedule": schedule,
            "prompts_sha256": general_eval.digest([
                judge_prompt({t["id"]: t for t in tasks}[control["task_id"]], control, order)
                for control in controls for order in ("ab", "ba")]),
            "scoring_sha256": general_eval.digest(Path(__file__).read_text(encoding="utf-8")),
            "general_eval_sha256": general_eval.digest(
                Path(general_eval.__file__).read_text(encoding="utf-8")),
            "adapter_sha256": adapter_hash, "api_config": api_config, "cli_config": cli_config,
            "policy": "Two fixed presentation orders per verified control; no retries or votes."}


def fixture_records(tasks, controls, plan):
    task_by_id = {task["id"]: task for task in tasks}
    control_by_id = {control["id"]: control for control in controls}
    rows = []
    for key in plan["schedule"]:
        control = control_by_id[key["control_id"]]
        expected = control["expected"]
        if key["order"] == "ba" and expected in {"A", "B"}:
            expected = "B" if expected == "A" else "A"
        prompt = judge_prompt(task_by_id[control["task_id"]], control, key["order"])
        rows.append({"version": VERSION, **key, "prompt": prompt,
                     "prompt_sha256": general_eval.digest(prompt), "source": "fixture",
                     "raw": general_eval.encoded({"winner": expected}),
                     "plan_sha256": general_eval.digest(plan), "execution_status": "completed",
                     "request_sent": False, "latency_seconds": None})
    return rows


def generate(tasks, controls, plan, output, api_config=None, cli_config=None, cli_executable=None):
    if plan != make_plan(tasks, controls, plan["model"], api_config, cli_config):
        raise ValueError("Judge plan differs from current controls, code, adapter, or configuration")
    task_by_id = {task["id"]: task for task in tasks}
    control_by_id = {control["id"]: control for control in controls}
    key = testgen_api.api_key(api_config) if api_config else None
    stopped = None
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        for logical in plan["schedule"]:
            control = control_by_id[logical["control_id"]]
            prompt = judge_prompt(task_by_id[control["task_id"]], control, logical["order"])
            record = {"version": VERSION, **logical, "prompt": prompt,
                      "prompt_sha256": general_eval.digest(prompt),
                      "plan_sha256": general_eval.digest(plan),
                      "source": "api" if api_config else "cli",
                      "requested_at": datetime.now(UTC).isoformat()}
            stopped = general_eval._execute_request(
                record, stopped, api_config, cli_config, cli_executable, plan["model"], prompt,
                key, "Skipped after blocking transport response; no retry was made")
            handle.write(general_eval.encoded(record) + "\n")
            handle.flush()


def _parse_winner(raw):
    try:
        if not isinstance(raw, str) or len(raw.encode()) > MAX_PAYLOAD:
            raise ValueError("Invalid judge response size")
        def unique_object(pairs):
            if len({key for key, _ in pairs}) != len(pairs):
                raise ValueError("Duplicate JSON object key")
            return dict(pairs)

        value = json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_object)
        if type(value) is not dict or set(value) != {"winner"} or value["winner"] not in {
                "A", "B", "TIE"}:
            raise ValueError("Judge response must contain exactly winner A, B, or TIE")
        return value["winner"], None
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        return None, str(exc)


def evaluate(tasks, controls, records, plan):
    expected = make_plan(tasks, controls, plan["model"], plan.get("api_config"),
                         plan.get("cli_config"))
    if not general_eval._replay_plan_matches(plan, expected):
        raise ValueError("Judge plan is not compatible with current code and controls")
    task_by_id = {task["id"]: task for task in tasks}
    control_by_id = {control["id"]: control for control in controls}
    expected = {general_eval.encoded(key) for key in plan["schedule"]}
    seen, rows = set(), []
    sources = {record.get("source") for record in records}
    if len(sources) != 1 or not sources <= {"api", "cli", "fixture"}:
        raise ValueError("A judge run must use one known source")
    general_eval.validate_model_identity(records)
    for record in records:
        key = {name: record.get(name) for name in
               ("system", "control_id", "order", "condition", "sample")}
        key_text = general_eval.encoded(key)
        if key_text in seen or key_text not in expected:
            raise ValueError("Duplicate or unexpected judge logical key")
        seen.add(key_text)
        control = control_by_id[key["control_id"]]
        prompt = judge_prompt(task_by_id[control["task_id"]], control, key["order"])
        if (record.get("version") != VERSION or record.get("prompt") != prompt or
                record.get("prompt_sha256") != general_eval.digest(prompt) or
                record.get("plan_sha256") != general_eval.digest(plan)):
            raise ValueError("Judge record provenance differs from plan")
        if record.get("source") == "api":
            config = plan["api_config"]
            if (record.get("api_config") != config or record.get("request") !=
                    testgen_api.request_for(config, plan["model"], prompt)):
                raise ValueError("Judge API request provenance differs from plan")
        elif record.get("source") == "cli":
            if (record.get("cli_config") != plan["cli_config"] or record.get("cli_prompt") !=
                    testgen_cli.cli_prompt(prompt, general_eval.CLI_PREFIX)):
                raise ValueError("Judge CLI prompt provenance differs from plan")
        execution_status = general_eval.validate_execution_status(record)
        winner, parse_error = (None, record.get("generation_error")) if record.get(
            "generation_error") else _parse_winner(record.get("raw", ""))
        expected_winner = control["expected"]
        if key["order"] == "ba" and expected_winner in {"A", "B"}:
            expected_winner = "B" if expected_winner == "A" else "A"
        canonical = winner
        if key["order"] == "ba" and winner in {"A", "B"}:
            canonical = "B" if winner == "A" else "A"
        rows.append({**key, "kind": control["kind"], "split": control["split"],
                     "winner": winner, "canonical_winner": canonical,
                     "expected_winner": expected_winner, "correct": winner == expected_winner,
                     "judge_error": parse_error, "execution_status": execution_status,
                     "raw": record.get("raw", "")})
    if seen != expected:
        raise ValueError(f"Judge run is incomplete: {len(expected - seen)} records missing")
    by_control = {}
    for control in controls:
        pair = [row for row in rows if row["control_id"] == control["id"]]
        by_control[control["id"]] = (None if any(row["judge_error"] for row in pair) else
                                      len({row["canonical_winner"] for row in pair}) > 1)
    valid = [row for row in rows if row["judge_error"] is None]
    complete = not any(row["execution_status"] in {"skipped_after_block", "harness_error"}
                       for row in rows)
    split_summary = {}
    for split in ("calibration", "test"):
        split_rows = [row for row in rows if row["split"] == split]
        valid_split = [row for row in split_rows if row["judge_error"] is None]
        split_summary[split] = {"presentations": len(split_rows), "valid": len(valid_split),
                                "scheduled_success_rate": round(sum(row["correct"] for row in
                                                                    split_rows) /
                                                                len(split_rows), 4),
                                "valid_presentation_accuracy": round(
                                    sum(row["correct"] for row in valid_split) /
                                    len(valid_split), 4) if valid_split else None}
    non_equivalent = [row for row in valid if row["kind"] != "equivalent"]
    equivalent = [row for row in valid if row["kind"] == "equivalent"]
    return {"kind": "general_judge_controls", "version": VERSION,
            "model": plan["model"], "plan_sha256": general_eval.digest(plan),
            "source": next(iter(sources)), "run_complete": complete,
            "controls": len(controls), "presentations": len(rows),
            "valid_presentations": len(valid),
            "scheduled_success_rate": (round(sum(row["correct"] for row in rows) / len(rows), 4)
                                       if complete else None),
            "valid_presentation_accuracy": (round(sum(row["correct"] for row in valid) /
                                                   len(valid), 4) if valid else None),
            "judge_errors": len(rows) - len(valid),
            "false_accepts": sum(not row["correct"] for row in non_equivalent),
            "false_accept_denominator": len(non_equivalent),
            "false_rejects": sum(not row["correct"] for row in equivalent),
            "false_reject_denominator": len(equivalent),
            "valid_order_pairs": sum(value is not None for value in by_control.values()),
            "order_flips": sum(value is True for value in by_control.values()),
            "splits": split_summary, "rows": rows,
            "note": "Author-written deterministic controls; not human validation. Judge results are not candidate task scores."}


def write_report(report, path):
    if path.suffix != ".json":
        raise ValueError("Report output must end in .json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def print_report(report):
    rate = lambda value: "unavailable" if value is None else f"{value:.1%}"
    print("General judge controls")
    print(f"Model: {report['model']}")
    print(f"Source: {report['source']}")
    if report["source"] == "fixture":
        print("Reference fixture: no model calls were made.")
    print(f"Scope: {report['controls']} controls, {report['presentations']} presentations")
    print(f"Status: {'complete' if report['run_complete'] else 'incomplete'}")
    print("Metrics: "
          f"scheduled success {rate(report['scheduled_success_rate'])}; "
          f"valid-response accuracy {rate(report['valid_presentation_accuracy'])}; "
          f"valid {report['valid_presentations']}/{report['presentations']}; "
          f"judge errors {report['judge_errors']}; order flips {report['order_flips']}")
    print("Error rates: "
          f"false accepts {report['false_accepts']}/{report['false_accept_denominator']}; "
          f"false rejects {report['false_rejects']}/{report['false_reject_denominator']}")
    failed = [row for row in report["rows"] if not row["correct"]]
    if failed:
        print("Failed items:")
        for row in failed:
            detail = row["judge_error"] or f"winner {row['winner']}, expected {row['expected_winner']}"
            print(f"  {row['control_id']} / {row['order']}: "
                  f"{row['execution_status']} ({detail})")
    else:
        print("Failed items: none")
    print(f"Limitation: {report['note']}")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate")
    for name in ("freeze", "generate"):
        item = commands.add_parser(name)
        general_eval.add_transport_arguments(item)
        if name == "generate":
            item.add_argument("--plan", type=Path, required=True)
            item.add_argument("--cli-executable")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--plan", type=Path, required=True)
    evaluate.add_argument("--generations", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, help="Optional JSON report path")
    demo = commands.add_parser("demo")
    demo.add_argument("--directory", type=Path,
                      help="Optional directory for fixture JSON artifacts")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    tasks, controls = general_eval.load_tasks(), load_controls()
    if args.command == "validate":
        print(json.dumps(validate_controls(tasks, controls), indent=2))
        return
    if args.command in {"freeze", "generate"}:
        api_config, cli_config = general_eval.transport_configuration(args)
        if args.command == "freeze":
            plan = make_plan(tasks, controls, args.model, api_config, cli_config)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(plan, indent=2) + "\n")
        else:
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            if args.model != plan["model"]:
                raise ValueError("Judge generation model differs from the frozen plan")
            generate(tasks, controls, plan, args.output, api_config, cli_config,
                     args.cli_executable)
        return
    if args.command == "evaluate":
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        records = [json.loads(line) for line in args.generations.read_text(
            encoding="utf-8").splitlines() if line.strip()]
        report = evaluate(tasks, controls, records, plan)
        print_report(report)
        if args.output:
            write_report(report, args.output)
            print(f"JSON report: {args.output}")
        return
    api_config = testgen_api.configuration("openai")
    plan = make_plan(tasks, controls, "reference-fixture", api_config=api_config)
    records = fixture_records(tasks, controls, plan)
    report = evaluate(tasks, controls, records, plan)
    print_report(report)
    if args.directory:
        args.directory.mkdir(parents=True, exist_ok=True)
        plan_path = args.directory / "judge-fixture-plan.json"
        raw_path = args.directory / "judge-fixture-generations.jsonl"
        report_path = args.directory / "judge-fixture-report.json"
        plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        raw_path.write_text("".join(general_eval.encoded(row) + "\n" for row in records),
                            encoding="utf-8")
        write_report(report, report_path)
        print(f"Fixture artifacts: {args.directory}")


if __name__ == "__main__":
    main()
