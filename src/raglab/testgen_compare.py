"""Side-by-side reports from independently replayed model runs; no network access."""
import json


def comparison_report(reports):
    if len(reports) < 2:
        raise ValueError("Comparison requires at least two generation files")
    scope = ("dataset_sha256", "version", "selected_tasks", "splits")
    if any(any(report[key] != reports[0][key] for key in scope) for report in reports[1:]):
        raise ValueError("Comparison requires identical dataset, protocol, tasks and splits")
    if any(report["source"] == "reference_fixture" for report in reports):
        raise ValueError("Reference fixtures are runner checks and cannot enter model comparisons")
    report = {"kind": "model_comparison", **{key: reports[0][key] for key in scope},
              "runs": reports}
    return report


def write_comparison(reports, path):
    if path.suffix != ".json":
        raise ValueError("Comparison report must end in .json")
    report = comparison_report(reports)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def print_comparison(report):
    print("Test-generation model comparison")
    print(f"Scope: {len(report['runs'])} runs, {len(report['selected_tasks'])} tasks, "
          f"protocol {report['version']}")
    for run in report["runs"]:
        provider = (run.get("api_config") or run.get("cli_config") or {}).get(
            "provider", run["source"])
        print(f"Model: {provider} / {run['model']}")
        failed = [row for row in run["rows"] if row["status"] != "valid"]
        print(f"  Status: {'complete' if not failed else 'completed with failed suites'}")
        for condition, item in run["summary"].items():
            print(f"  {condition}: {item['mutants_killed']}/{item['mutants_total']} bugs "
                  f"({item['mutation_score']:.1%}); valid {item['valid']}/{item['suites']}; "
                  f"failed suites {item['suites'] - item['valid']}")
        if failed:
            print("  Failed items:")
            for row in failed:
                print(f"    {row['task_id']}/{row['condition']}: {row['status']}")
        else:
            print("  Failed items: none")
    print("Limitation: descriptive results on the same synthetic tasks. Provider settings and "
          "hardware may differ; these scores do not establish a general model ranking. "
          "Generation failures stay in the denominator. No cost estimates are inferred.")
