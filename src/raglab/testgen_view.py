"""Local, self-contained report view. Based on the reviewed Grok rendering proposal."""
import html
import json

CSS = """
:root{color-scheme:light;--ink:#16324a;--muted:#526475;--line:#d7e0e8;--blue:#1768a3}
*{box-sizing:border-box}body{margin:0;background:#f4f7f9;color:var(--ink);
font:16px/1.55 system-ui,Segoe UI,sans-serif}main{max-width:1180px;margin:auto;padding:3rem 1.5rem}
header{border-bottom:1px solid var(--line);padding-bottom:1.5rem}.eyebrow{font-size:.75rem;
letter-spacing:.14em;font-weight:750;color:var(--blue)}h1{font-size:clamp(2rem,4vw,3.3rem);
line-height:1.1;max-width:850px;margin:.65rem 0 1rem;letter-spacing:-.04em}
h2{font-size:1.15rem;margin:.25rem 0}.muted,footer{color:var(--muted)}
.meta{display:flex;flex-wrap:wrap;gap:.5rem;margin:1.2rem 0}.meta span{background:white;
padding:.3rem .7rem;border:1px solid var(--line);border-radius:30px;font-size:.8rem}
.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem;margin:1.5rem 0}
.card{background:white;border:1px solid var(--line);padding:1.5rem;border-radius:12px}
.score{font-size:3.25rem;line-height:1.2;font-weight:750;letter-spacing:-.04em}
.track{height:8px;background:#e7edf2;border-radius:4px;margin:1rem 0}.track span{display:block;
height:100%;background:var(--blue);border-radius:4px}.stats{display:grid;
grid-template-columns:1fr 1fr;gap:1rem}.stats b{display:block;font-size:1.25rem}
.stats span{font-size:.8rem;color:var(--muted)}.finding{border-left:4px solid var(--blue);
background:#e9f2f8;padding:1rem 1.25rem;margin:1.5rem 0}.fixture{background:#fff1cc;padding:1rem}
table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{padding:.85rem .65rem;
text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}
th{font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
tbody>tr:nth-child(odd){background:#fff}summary{cursor:pointer;color:var(--blue);
font-weight:650}summary:focus-visible,a:focus-visible{outline:3px solid #ce6800;outline-offset:3px}
.pass{color:#166534;font-weight:650}.fail{color:#a62c23;font-weight:650}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.8rem;background:#eef2f5;
padding:.7rem;border-radius:6px}code{overflow-wrap:anywhere;font-size:.85em}
.wide{overflow-x:auto}footer{font-size:.8rem;margin-top:2rem}
@media(max-width:700px){main{padding:1.5rem .8rem}.cards{grid-template-columns:1fr}
.card{padding:1rem}.stats{gap:.6rem}th,td{padding:.65rem .4rem}}
"""


def esc(value):
    return html.escape(str(value), quote=True)


def pretty(value):
    return esc(json.dumps(value, ensure_ascii=False, indent=2))


def evidence(row):
    parts = []
    if row.get("error"):
        parts.append(f'<p class="fail">{esc(row["error"])}</p>')
    if row.get("correct", {}).get("error"):
        parts.append(f'<p class="fail">{esc(row["correct"]["error"])}</p>')
    outcomes = row.get("correct", {}).get("outcomes", [])
    for index, case in enumerate(row.get("tests", [])):
        result = outcomes[index] if index < len(outcomes) else None
        label = "Not evaluated" if result is None else "Passed" if result["passed"] else "Failed"
        style = "muted" if result is None else "pass" if result["passed"] else "fail"
        parts.append(f'<p class="{style}">Test {index + 1}: {label}</p>'
                     f'<pre>{pretty({"generated": case, "observed": result})}</pre>')
    killed = ", ".join(row["killed"]) or "None"
    parts.append(f"<p>Credited bug IDs: <code>{esc(killed)}</code></p>")
    if row.get("mutant_results"):
        parts.append("<details><summary>Seeded bug execution details</summary>"
                     f'<pre>{pretty(row["mutant_results"])}</pre></details>')
    if row.get("api_metadata"):
        parts.append("<details><summary>API response metadata</summary>"
                     f'<pre>{pretty(row["api_metadata"])}</pre></details>')
    parts.append("<details><summary>Raw model response</summary>"
                 f'<pre>{esc(row.get("raw", ""))}</pre></details>')
    return '<details><summary>Inspect evidence</summary>' + "".join(parts) + "</details>"


def render_html(report):
    fixture = report["source"] == "reference_fixture"
    heldout = report.get("plan_sha256") and report["splits"] == ["test"]
    experiment = "Frozen held-out experiment" if heldout else "Development experiment"
    if fixture:
        experiment = "Offline runner check"
    config = report.get("api_config") or report.get("cli_config")
    if config and heldout:
        experiment = "Frozen request settings / public test split"
    runtime = (f"API: {config['provider']}" if config else
               "Reference fixture" if fixture else
               f"Ollama {report.get('runtime_version') or 'version not recorded'}")
    api_details = ("<details><summary>API configuration</summary>"
                   f"<pre>{pretty(config)}</pre>"
                   "<p>Only request settings are frozen. Remote model weights cannot be verified. "
                   "JSON is validated locally; native format constraints depend on these settings. "
                   "Output token totals include reported reasoning tokens.</p></details>") if config else ""
    if report.get("cli_config"):
        runtime = f"Subscription CLI: {config['provider']}"
        api_details = ("<details><summary>Subscription CLI configuration</summary>"
                       f"<pre>{pretty(config)}</pre><p>Fresh prompt-only sessions. CLI system prompts "
                       "and defaults remain part of the experiment. Tool use disqualifies a suite; "
                       "these results measure the model through this CLI, not the raw API.</p></details>")
    labels = {"code_only": "Code only", "code_docs": "Code + documentation"}
    cards = []
    for condition, item in report["summary"].items():
        score = item["mutation_score"]
        invalid = item["invalid_generation"] + item["generation_error"] + item["execution_error"]
        latency = item["median_latency_seconds"]
        latency = "Unavailable" if latency is None else f"{latency:.1f}s"
        cards.append(
            f'<article class="card"><h2>{labels[condition]}</h2>'
            f'<div class="score">{score:.1%}</div>'
            f'<div class="muted">{item["mutants_killed"]} of {item["mutants_total"]} seeded bugs found</div>'
            f'<div class="track" aria-hidden="true"><span style="width:{score * 100:.2f}%"></span></div>'
            '<div class="stats">'
            f'<div><b>{item["valid"]}/{item["suites"]}</b><span>Valid test suites</span></div>'
            f'<div><b>{item["false_alarm"]}</b><span>Suites with wrong assertions</span></div>'
            f'<div><b>{invalid}</b><span>Format / provider / execution failures</span></div>'
            f'<div><b>{latency}</b><span>Median generation time</span></div></div></article>'
        )
    rows = []
    for row in report["rows"]:
        status = row["status"].replace("_", " ")
        style = "pass" if row["status"] == "valid" else "fail"
        rows.append(
            f'<tr><td><strong>{esc(row["task_id"])}</strong></td>'
            f'<td>{labels[row["condition"]]}</td><td class="{style}">{esc(status)}</td>'
            f'<td>{len(row["killed"])}/{row["mutants"]}</td><td>{evidence(row)}</td></tr>'
        )
    comparison = report["comparison"]
    low, high = comparison["task_bootstrap_95_ci"]
    banner = ('<p class="fixture"><strong>Reference fixture: no LLM was used.</strong> '
              'This checks the runner and is not model-performance evidence.</p>') if fixture else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>Test Generation Lab — {esc(report["model"])}</title><style>{CSS}</style></head>'
        '<body><main><header><div class="eyebrow">RELIABILITY LAB / TEST GENERATION</div>'
        '<h1>Can better context produce better tests?</h1>'
        '<p class="muted">A paired comparison of generated tests, scored against correct '
        'functions and deliberately seeded bugs.</p>'
        f'<div class="meta"><span>{esc(report["model"])}</span>'
        f'<span>{len(report["selected_tasks"])}/{report["dataset_tasks"]} tasks</span>'
        f'<span>Split: {esc(", ".join(report["splits"]))}</span>'
        f'<span>{esc(report["version"])}</span><span>{experiment}</span>'
        f'<span>{esc(runtime)}</span>'
        f'</div></header>{banner}{api_details}'
        f'<section class="cards">{"".join(cards)}</section>'
        '<p>A suite earns bug-detection credit only when <strong>every assertion passes the '
        'correct implementation</strong>. Wrong assertions and malformed suites earn zero. '
        'Execution failures never count as detected bugs.</p>'
        '<section class="finding"><h2>Documentation minus code-only score</h2>'
        f'<strong>{comparison["mean_docs_minus_code"] * 100:+.1f} percentage points</strong>'
        f' · 95% task-bootstrap interval: {low * 100:+.1f} to {high * 100:+.1f} points.'
        f'<div>{comparison["docs_wins"]} documentation wins · {comparison["ties"]} ties · '
        f'{comparison["code_wins"]} code-only wins</div>'
        '<small>Exploratory: a small synthetic dataset and one generation per condition. '
        'This interval resamples tasks, not model generations. Timing includes warm-up effects.</small>'
        '</section><h2>Inspect every result</h2>'
        '<p class="muted">Expand a row to compare generated assertions with observed behavior.</p>'
        '<div class="wide"><table><thead><tr><th>Function</th><th>Context</th><th>Suite result</th>'
        f'<th>Bugs found</th><th>Evidence</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
        '<footer>Dataset SHA-256: '
        f'<code>{esc(report["dataset_sha256"])}</code>'
        f'<p>Model digest: <code>{esc(report.get("model_digest") or "Unavailable")}</code><br>'
        f'Frozen plan SHA-256: <code>{esc(report.get("plan_sha256") or "Not applicable")}</code></p>'
        '<p>Model results above are separate from '
        'the repository software tests. Local HTML report; no remote assets or tracking.</p>'
        '</footer></main></body></html>'
    )
