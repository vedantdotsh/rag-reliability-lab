"""Side-by-side reports from independently replayed model runs; no network access."""
import json
from pathlib import Path

from raglab.testgen_view import CSS, esc, pretty


def write_comparison(reports, path):
    if len(reports) < 2:
        raise ValueError("Comparison requires at least two generation files")
    if path.suffix != ".json":
        raise ValueError("Comparison report must end in .json")
    scope = ("dataset_sha256", "version", "selected_tasks", "splits")
    if any(any(report[key] != reports[0][key] for key in scope) for report in reports[1:]):
        raise ValueError("Comparison requires identical dataset, protocol, tasks and splits")
    if any(report["source"] == "reference_fixture" for report in reports):
        raise ValueError("Reference fixtures are runner checks and cannot enter model comparisons")
    report = {"kind": "model_comparison", **{key: reports[0][key] for key in scope}, "runs": reports}
    note = ("Descriptive results on the same synthetic tasks. Provider defaults, native JSON "
            "constraints, tokenizers, reasoning budgets and hardware may differ. See each run's "
            "settings; these scores do not isolate model capability or establish a general ranking. "
            "All generation failures remain in the score denominator. No cost estimates are inferred.")
    headers = ["Provider / model", "Prompt", "Bugs caught", "Score", "Valid suites",
               "Wrong assertions", "Other failures", "Median seconds", "Input / output tokens"]
    table = []
    details = []
    for index, run in enumerate(reports, 1):
        provider = (run.get("api_config") or run.get("cli_config") or {}).get("provider", run["source"])
        label = f"{provider} / {run['model']}"
        for condition, item in run["summary"].items():
            failures = sum(item[k] for k in ("invalid_generation", "generation_error", "execution_error"))
            latency = item["median_latency_seconds"]
            tokens = ["?" if item[k] is None else str(item[k])
                      for k in ("prompt_tokens", "completion_tokens")]
            table.append([label, condition, f"{item['mutants_killed']}/{item['mutants_total']}",
                          f"{item['mutation_score']:.1%}", f"{item['valid']}/{item['suites']}",
                          str(item["false_alarm"]), str(failures),
                          "?" if latency is None else str(latency), " / ".join(tokens)])
        settings = {key: run.get(key) for key in (
            "model", "model_digest", "api_config", "cli_config", "options", "think", "runtime_version",
            "plan_sha256")}
        details.append(f"<details><summary>Run {index}: {esc(label)} — settings</summary>"
                       f"<pre>{pretty(settings)}</pre></details>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    # Escape user-selected names for Markdown as well as HTML.
    def md(value):
        return esc(value).replace("|", "&#124;").replace("\n", " ")
    lines = ["# Model comparison", "", note, "",
             "| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    lines.extend("| " + " | ".join(map(md, row)) + " |" for row in table)
    lines += ["", "Full run settings and replayed evidence are in the companion JSON."]
    path.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    cells = "".join("<tr>" + "".join(f"<td>{esc(cell)}</td>" for cell in row) + "</tr>" for row in table)
    html = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>Test Generation Lab — model comparison</title><style>{CSS}</style>'
        '<main><header><div class="eyebrow">RELIABILITY LAB / MODEL COMPARISON</div>'
        f'<h1>Same tasks. Different models.</h1><p>{len(reports)} runs · '
        f'{len(report["selected_tasks"])} tasks · {esc(report["version"])}</p></header>'
        f'<p>{esc(note)}</p><div class="wide"><table><thead><tr>'
        + "".join(f"<th>{esc(h)}</th>" for h in headers)
        + f'</tr></thead><tbody>{cells}</tbody></table></div><h2>Recorded settings</h2>'
        + "".join(details) + f'<footer>Dataset: <code>{esc(report["dataset_sha256"])}</code>'
        '<p>Missing token counts are shown as ?. Output totals include reported reasoning tokens. '
        'These public synthetic tasks are not new unseen evidence. Full replayed evidence is in the '
        'companion JSON; evaluate a run separately for its interactive evidence report.</p></footer></main></html>'
    )
    Path(path).with_suffix(".html").write_text(html, encoding="utf-8")
