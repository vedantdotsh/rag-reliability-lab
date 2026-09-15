"""Freeze and run the current Codex/Cursor catalog through existing CLI logins."""
import argparse
import concurrent.futures
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from raglab import testgen, testgen_cli
from raglab.testgen_compare import print_comparison, write_comparison


def read_cli(command):
    return subprocess.check_output(command, encoding="utf-8", errors="replace").strip()


def family(model):
    name = model.removesuffix("-fast")
    for _ in range(3):
        name = re.sub(r"-(?:extra-high|xhigh|high|medium|low|none|minimal|max|thinking)$", "", name)
    return name


def inventory(cursor, codex, cache):
    cursor_command = ["powershell.exe", "-NoProfile", "-File", str(cursor)]
    catalog = read_cli([*cursor_command, "--list-models"])
    available = [line.split(" - ", 1)[0] for line in catalog.splitlines() if " - " in line]
    groups = {}
    for model in available:
        if model != "auto" and not model.endswith("-fast"):
            groups.setdefault(family(model), []).append(model)
    chosen = []
    for base, variants in groups.items():
        preferred = [base, base + "-medium", base + "-medium-thinking", base + "-thinking-medium",
                     base + "-high", base + "-thinking-high"]
        if base == "cursor-grok-4.6":
            preferred.insert(0, "cursor-grok-4.6-xhigh")
        chosen.append(next((model for model in preferred if model in variants), variants[0]))
    codex_models = json.loads(cache.read_text(encoding="utf-8"))["models"]
    models = [{"provider": "codex", "model": model["slug"], "effort": "medium"}
              for model in codex_models if model.get("visibility") == "list"]
    models += [{"provider": "cursor", "model": model, "effort": None} for model in chosen]
    return {"created_at": datetime.now(UTC).isoformat(), "models": models,
            "cursor_catalog": available,
            "selection": "One standard-speed setting per distinct model family; prefer medium/default. "
                         "Grok 4.6 uses the user's Extra High preference. Auto is not a fixed model.",
            "versions": {"codex": read_cli([str(codex), "--version"]),
                         "cursor": read_cli([*cursor_command, "--version"])}}


def run_model(tasks, entry, versions, executables, directory):
    provider, model = entry["provider"], entry["model"]
    stem = provider + "-" + model
    output = directory / (stem + ".jsonl")
    report_path = directory / (stem + ".json")
    if output.exists():
        # Never repeat generation for an existing attempt. Incomplete attempts require inspection.
        records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
        if len(records) != 32:
            raise ValueError(f"Incomplete attempt preserved without retry: {stem}")
        report = testgen.evaluate(tasks, records)
        testgen.write_report(report, report_path)
        return report
    config = testgen_cli.configuration(provider, versions[provider], entry.get("effort") or "medium")
    plan = {"created_at": datetime.now(UTC).isoformat(), "configuration": testgen.make_plan(
        tasks, model, None, runtime_version=versions[provider], cli_config=config)}
    with (directory / (stem + "-plan.json")).open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(plan, indent=2) + "\n")
    selected = [task for task in tasks if task["split"] == "test"]
    testgen.generate(tasks, selected, output, model, None, plan=plan,
                     cli_config=config, cli_executable=str(executables[provider]))
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    report = testgen.evaluate(tasks, records)
    testgen.write_report(report, report_path)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cursor", type=Path, required=True)
    parser.add_argument("--codex", type=Path, default=shutil.which("codex"))
    parser.add_argument("--model-cache", type=Path, default=Path.home() / ".codex/models_cache.json")
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--provider", choices=("codex", "cursor"))
    parser.add_argument("--models", nargs="+", help="Run only these exact IDs from the saved catalog")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("Choose 1 to 4 workers")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = args.output_dir / "inventory.json"
    if inventory_path.exists():
        catalog = json.loads(inventory_path.read_text(encoding="utf-8"))
    else:
        catalog = inventory(args.cursor, args.codex, args.model_cache)
        with inventory_path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(catalog, indent=2) + "\n")
    models = [entry for entry in catalog["models"]
              if (args.provider is None or entry["provider"] == args.provider)
              and (args.models is None or entry["model"] in args.models)]
    if args.models and set(args.models) - {entry["model"] for entry in models}:
        parser.error("--models must contain exact IDs available for the selected provider")
    print(f"Selected {len(models)} models; 32 independent prompts per model", flush=True)
    if args.inventory_only:
        for entry in models:
            print(entry["provider"], entry["model"])
        return
    tasks = testgen.load_tasks()
    executables = {"codex": args.codex, "cursor": args.cursor}
    reports, errors = [], []
    progress_path = args.output_dir / ((args.provider or "all") + "-progress.json")
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_model, tasks, entry, catalog["versions"], executables,
                               args.output_dir): entry for entry in models}
        for future in concurrent.futures.as_completed(futures):
            entry = futures[future]
            try:
                report = future.result()
                reports.append(report)
                print(f"COMPLETE {entry['provider']} {entry['model']}", flush=True)
                testgen.print_report(report)
            except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
                errors.append({**entry, "error": str(exc)})
                print("FAILED", entry["provider"], entry["model"], str(exc), flush=True)
            progress = {"updated_at": datetime.now(UTC).isoformat(), "total": len(models),
                        "completed": [r["model"] for r in reports], "errors": errors}
            progress_path.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
            if len(reports) >= 2:
                comparison = write_comparison(
                    reports, args.output_dir / ((args.provider or "all") + "-comparison.json"))
    if len(reports) >= 2:
        print_comparison(comparison)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
