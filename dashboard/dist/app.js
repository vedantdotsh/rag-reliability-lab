"use strict";

const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
const number = (value) => typeof value === "number" && Number.isFinite(value);
const percent = (value) => number(value) ? `${(value * 100).toFixed(1)}%` : "N/A";
const millis = (value) => number(value) ? `${value.toFixed(2)} ms` : "N/A";
const titleCase = (value) => String(value).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
const timeLabel = (value) => new Date(value).toLocaleString(undefined, {month:"short",day:"numeric",hour:"2-digit",minute:"2-digit",second:"2-digit"});
const labels = {hit_rate_at_3:"Evidence hit @3",mean_reciprocal_rank:"Reciprocal rank",source_recall_at_3:"Source recall @3",required_phrase_coverage:"Phrase coverage",faithfulness:"Source faithfulness",citation_correctness:"Citation IDs",answerable_response_rate:"Answerable response",unanswerable_abstention_rate:"Correct abstention"};
let runs = [], current = null, filteredCases = [], signature = "", loading = false;

function setNotice(message) { $("notice").hidden = !message; $("notice").textContent = message; }
function selectedRun() { return $("run-select").value === "latest" ? runs[0] : runs.find((run) => String(run.id) === $("run-select").value); }
function sameBenchmark(a, b) { return a?.report?.benchmark_sha256 && a.report.benchmark_sha256 === b?.report?.benchmark_sha256 && a.report.schema_version === b.report.schema_version; }
function runLabel(run) { return `#${run.id} · ${timeLabel(run.created_at)} · ${run.trigger}`; }

function updateSelectors() {
  const selected = $("run-select").value || "latest";
  $("run-select").innerHTML = '<option value="latest">Follow latest run</option>' + runs.map((run) => `<option value="${Number(run.id)}">${escapeHtml(runLabel(run))}</option>`).join("");
  $("run-select").value = selected === "latest" || runs.some((run) => String(run.id) === selected) ? selected : "latest";
  updateComparison();
}

function updateComparison() {
  current = selectedRun();
  const previous = $("compare-select").value;
  const comparable = runs.filter((run) => run.id !== current?.id && sameBenchmark(run, current));
  $("compare-select").innerHTML = '<option value="none">No comparison</option>' + comparable.map((run) => `<option value="${Number(run.id)}">${escapeHtml(runLabel(run))}</option>`).join("");
  $("compare-select").value = previous === "none" ? "none" : comparable.some((run) => String(run.id) === previous) ? previous : String(comparable.find((run) => run.id < current.id)?.id ?? "none");
}

function render() {
  current = selectedRun();
  if (!current) return;
  const report = current.report, metrics = report?.metrics || {}, cases = report?.cases || [];
  const compared = runs.find((run) => String(run.id) === $("compare-select").value);
  $("compare-legend").hidden = !compared;
  setNotice(current.error ? `This run could not complete its evaluation: ${current.error}` : "");
  $("provenance").textContent = report ? `${report.dataset_size} benchmark questions · ${cases.filter((c) => !c.should_abstain).length} answerable · ${cases.filter((c) => c.should_abstain).length} unanswerable` : "Evaluation unavailable for this run. Software test results are shown separately.";
  $("run-context").textContent = `${runLabel(current)} · ${report ? `top ${report.config.top_k} context` : "No evaluation"}`;
  $("benchmark-id").textContent = report ? `Benchmark ${report.benchmark_sha256.slice(0, 12)} · schema ${report.schema_version}` : "";
  const gate = current.gate;
  $("gate-value").textContent = gate ? (gate.passed ? "Passed" : "Failed") : "Unavailable";
  $("gate-value").className = `kpi-value ${gate?.passed ? "good-text" : "bad-text"}`;
  document.querySelector(".gate-card").classList.toggle("is-pass", !!gate?.passed);
  $("gate-description").textContent = gate ? `${gate.checks.filter((c) => c.passed).length} of ${gate.checks.length} quality thresholds met` : "No gate result was produced.";
  $("coverage-value").textContent = percent(metrics.required_phrase_coverage);
  const oldCoverage = compared?.report?.metrics?.required_phrase_coverage;
  $("coverage-description").textContent = number(oldCoverage) && number(metrics.required_phrase_coverage) ? `${((metrics.required_phrase_coverage - oldCoverage) * 100).toFixed(1)} percentage points vs run #${compared.id}` : "Literal phrase presence · answerable cases";
  $("abstention-value").textContent = percent(metrics.unanswerable_abstention_rate);
  const unknown = cases.filter((c) => c.should_abstain);
  $("abstention-description").textContent = unknown.length ? `${unknown.filter((c) => c.abstained).length} of ${unknown.length} unanswerable cases withheld` : "No unanswerable cases in this run.";
  const tests = current.tests;
  $("tests-value").textContent = tests ? (tests.exit_code === 0 ? `${tests.passed} passed` : `Exit ${tests.exit_code}`) : "Not run";
  $("tests-value").className = `kpi-value ${tests ? (tests.exit_code === 0 ? "good-text" : "bad-text") : ""}`;
  $("tests-description").textContent = tests ? `${tests.failed} failed · ${tests.errors} errors · ${tests.skipped} skipped · ${tests.collected} collected` : "Evaluation-only run; no test result implied.";
  $("quality-bars").innerHTML = Object.entries(labels).map(([key, label]) => {
    const value = metrics[key], check = gate?.checks.find((c) => c.metric === key && c.operator === ">="), old = compared?.report?.metrics?.[key];
    const width = number(value) ? Math.max(0, Math.min(100, value * 100)) : 0;
    const target = check && number(check.threshold) ? `<i class="target-tick" style="left:${Math.max(0,Math.min(100,check.threshold * 100))}%" title="Target: ${percent(check.threshold)}"></i>` : "";
    const comparison = number(old) ? `<i class="compare-tick" style="left:${Math.max(0,Math.min(100,old * 100))}%" title="Run #${compared.id}: ${percent(old)}"></i>` : "";
    return `<div class="quality-row"><span class="quality-label">${label}</span><div class="bar-track" role="img" aria-label="${label}: ${percent(value)}${check ? `, target ${percent(check.threshold)}` : ""}${number(old) ? `, comparison ${percent(old)}` : ""}"><div class="bar-fill ${check && !check.passed ? "missed" : ""}" style="width:${width}%"></div>${comparison}${target}</div><span class="bar-value">${percent(value)}</span></div>`;
  }).join("");
  const latencies = cases.map((c) => c.latency_ms).filter(number).sort((a,b) => a-b);
  $("p50").textContent = millis(latencies.length ? latencies[Math.ceil(latencies.length * .5) - 1] : null);
  $("p95").textContent = millis(metrics.p95_latency_ms);
  $("max-latency").textContent = millis(latencies.length ? latencies[latencies.length - 1] : null);
  renderTrend();
  renderCategories(cases);
  renderCases();
  $("history-note").textContent = `${runs.length} recorded runs shown · latest 100 · refresh every 5 seconds`;
}

function renderTrend() {
  const metric = $("trend-metric").value;
  const cohort = runs.filter((run) => sameBenchmark(run, current) && number(run.report.metrics[metric])).slice(0, 20).reverse();
  $("trend-caption").textContent = `${cohort.length} comparable ${cohort.length === 1 ? "run" : "runs"} · same data and labels${cohort.length === 20 ? " · latest 20" : ""}`;
  if (!cohort.length) { $("trend-chart").innerHTML = '<p class="empty-trend">No measurements for this metric.</p>'; return; }
  const latency = metric === "p95_latency_ms", fmt = latency ? millis : percent;
  const max = latency ? Math.max(.1, Math.ceil(Math.max(...cohort.map((r) => r.report.metrics[metric])) * 12) / 10) : 1;
  const width = $("trend-chart").clientWidth || 320;
  const left = 58, right = width - 22, top = 24, bottom = 215;
  const points = cohort.map((run, index) => ({run, x:cohort.length === 1 ? (left+right)/2 : left+(right-left)*index/(cohort.length-1), y:bottom-(bottom-top)*Math.max(0,Math.min(1,run.report.metrics[metric]/max))}));
  const grid = [0,.5,1].map((fraction) => { const y=bottom-(bottom-top)*fraction; return `<line x1="${left}" x2="${right}" y1="${y}" y2="${y}" stroke="#dde2e6" ${fraction ? 'stroke-dasharray="3 5"' : ""}/><text x="${left-12}" y="${y+4}" text-anchor="end" font-size="12" fill="#606c77">${latency ? (max*fraction).toFixed(2) : `${fraction*100}%`}</text>`; }).join("");
  const path = points.map((point,i) => `${i ? "L" : "M"}${point.x},${point.y}`).join(" ");
  const dots = points.map(({run,x,y}) => `<g data-run="${run.id}" tabindex="0" role="button" aria-label="View run ${run.id}, ${fmt(run.report.metrics[metric])}"><title>${escapeHtml(runLabel(run))}: ${fmt(run.report.metrics[metric])}</title><circle cx="${x}" cy="${y}" r="14" fill="transparent"/><circle cx="${x}" cy="${y}" r="${run.id === current.id ? 6 : 4}" fill="${run.id === current.id ? '#17232d' : '#245cdb'}" stroke="white" stroke-width="2"/></g>`).join("");
  const labelPoints = points.filter((_,i) => i === 0 || i === points.length-1 || (points.length > 5 && i === Math.floor(points.length/2)));
  const ticks = labelPoints.map(({run,x}) => `<text x="${x}" y="242" text-anchor="middle" font-size="12" fill="#606c77">Run #${run.id}</text>`).join("");
  $("trend-chart").innerHTML = `<svg viewBox="0 0 ${width} 260" aria-label="${escapeHtml($("trend-metric").selectedOptions[0].textContent)} across ${cohort.length} runs" role="group"><title>${cohort.length === 1 ? "One recorded run. Run tests again to build a trend." : "Select a point to inspect that run."}</title>${grid}<path d="${path}" fill="none" stroke="#245cdb" stroke-width="2" stroke-linejoin="round"/>${dots}${ticks}</svg>`;
}

function renderCategories(cases) {
  const groups = new Map();
  for (const item of cases) { const group=groups.get(item.category) || {total:0,issues:0}; group.total++; group.issues += (item.issues || []).length > 0 ? 1 : 0; groups.set(item.category,group); }
  $("diagnostic-summary").textContent = `${cases.filter((item) => item.issues.length).length} of ${cases.length} cases need review. Select a category to inspect.`;
  $("category-chart").innerHTML = [...groups].sort((a,b) => b[1].issues-a[1].issues).map(([name,group]) => `<div class="category-row"><button class="category-button" data-category="${escapeHtml(name)}">${escapeHtml(titleCase(name))}</button><div class="stacked-bar" role="img" aria-label="${escapeHtml(titleCase(name))}: ${group.issues} of ${group.total} cases need inspection"><span class="good" style="width:${(group.total-group.issues)/group.total*100}%"></span><span class="bad" style="width:${group.issues/group.total*100}%"></span></div><span class="category-count" title="${group.issues} of ${group.total} cases need review">${group.issues} / ${group.total}</span></div>`).join("") || '<p class="muted">No case results available.</p>';
  const selected = $("category-filter").value;
  $("category-filter").innerHTML = '<option value="all">All categories</option>' + [...groups.keys()].map((key) => `<option value="${escapeHtml(key)}">${escapeHtml(titleCase(key))}</option>`).join("");
  $("category-filter").value = groups.has(selected) ? selected : "all";
}

function renderCases() {
  const query = $("search").value.toLowerCase().trim(), category = $("category-filter").value;
  const cases = current?.report?.cases || [];
  filteredCases = cases.filter((c) => (!query || `${c.id} ${c.question} ${c.answer}`.toLowerCase().includes(query)) && (category === "all" || category === c.category) && (!$("issues-only").checked || c.issues.length));
  $("case-count").textContent = `${filteredCases.length} / ${cases.length}`;
  $("no-cases").hidden = !!filteredCases.length;
  $("download").disabled = !filteredCases.length;
  $("cases-body").innerHTML = filteredCases.map((item,i) => `<tr><td><button class="question-button" data-case="${i}">${escapeHtml(item.question)}</button><span class="row-meta">${escapeHtml(titleCase(item.category))} · ${escapeHtml(item.id)}</span></td><td>${percent(item.source_recall_at_3)}</td><td>${percent(item.required_phrase_coverage)}</td><td><span class="badge ${item.issues.length ? 'issue' : 'ok'}">${item.issues.length ? `${item.issues.length} ${item.issues.length === 1 ? 'issue' : 'issues'}` : 'No issues'}</span><span class="row-meta">${item.abstained ? 'Abstained' : 'Answered'}</span></td></tr>`).join("");
}

function openCase(index) {
  const item = filteredCases[index]; if (!item) return;
  $("case-id").textContent = `${item.id} · ${titleCase(item.category)}`;
  $("case-title").textContent = item.question;
  const list = (items, empty) => items.length ? `<ul class="detail-list">${items.map((v) => `<li>${escapeHtml(v)}</li>`).join("")}</ul>` : `<p class="muted">${empty}</p>`;
  $("case-detail").innerHTML = `<div class="detail-label">Generated answer · ${millis(item.latency_ms)}</div><div class="answer-block">${escapeHtml(item.answer)}</div><p class="muted">Expected: ${item.should_abstain ? 'abstention' : 'answer'} · Actual: ${item.abstained ? 'abstention' : 'answer'}</p><div class="detail-grid"><div><div class="detail-label">Retrieved source IDs</div>${list(item.retrieved_doc_ids,"No sources retrieved.")}</div><div><div class="detail-label">Expected source IDs</div>${list(item.expected_doc_ids,"Unanswerable; no expected source.")}</div></div><div class="detail-label">Required literal phrases</div>${list(item.required_facts,"No required phrases for an unanswerable case.")}<div class="detail-label">Source faithfulness: ${percent(item.faithfulness)} · Citation IDs: ${percent(item.citation_correctness)}</div>${item.issues.length ? `<div class="detail-issues">${list(item.issues,"")}</div>` : '<p class="muted">No diagnostic issues were recorded.</p>'}`;
  $("case-dialog").showModal();
}

async function refresh() {
  if (loading) return;
  loading = true; $("refresh").disabled = true;
  try {
    const response = await fetch("/api/runs", {cache:"no-store",signal:AbortSignal.timeout(8000)});
    if (!response.ok) throw new Error(`Server returned HTTP ${response.status}`);
    const data = await response.json();
    if (data.schema_version !== 1 || !Array.isArray(data.runs)) throw new Error("Unrecognized results format");
    const next = `${data.runs[0]?.id ?? "empty"}:${data.runs.length}`;
    runs = data.runs;
    $("empty").hidden = !!runs.length; $("workspace").hidden = !runs.length;
    $("connection").textContent = `Connected · checked ${new Date().toLocaleTimeString()}`;
    if (next !== signature) { signature = next; if(runs.length){ updateSelectors(); render(); } }
    else setNotice(current?.error ? `This run could not complete its evaluation: ${current.error}` : "");
  } catch(error) { $("connection").textContent = "Disconnected"; setNotice(`Unable to refresh results. ${runs.length ? 'Showing the last loaded run. ' : ''}${error.message}. Keep the local dashboard server running.`); }
  finally { loading = false; $("refresh").disabled = false; }
}

$("refresh").addEventListener("click", refresh);
$("run-select").addEventListener("change", () => { $("compare-select").value=""; updateComparison(); render(); });
$("compare-select").addEventListener("change", render);
$("trend-metric").addEventListener("change", renderTrend);
$("search").addEventListener("input", renderCases);
$("category-filter").addEventListener("change", renderCases);
$("issues-only").addEventListener("change", renderCases);
$("category-chart").addEventListener("click", (event) => { const button=event.target.closest("[data-category]"); if(button){ $("category-filter").value=button.dataset.category; renderCases(); document.querySelector(".cases-panel").scrollIntoView({block:"start"}); } });
$("cases-body").addEventListener("click", (event) => { const button=event.target.closest("[data-case]"); if(button) openCase(Number(button.dataset.case)); });
function selectPoint(event) { const point=event.target.closest("[data-run]"); if(point){ $("run-select").value=point.dataset.run; $("compare-select").value=""; updateComparison(); render(); } }
$("trend-chart").addEventListener("click", selectPoint);
$("trend-chart").addEventListener("keydown", (event) => { if(event.key === "Enter" || event.key === " "){ event.preventDefault(); selectPoint(event); } });
$("close-dialog").addEventListener("click", () => $("case-dialog").close());
$("download").addEventListener("click", () => {
  const headers = ["id","category","question","answer","should_abstain","abstained","source_recall_at_3","required_phrase_coverage","faithfulness","citation_correctness","latency_ms","issues"];
  const cell = (value) => { let text=String(value ?? ""); if(/^[\s]*[=+\-@]/.test(text)) text="'"+text; return '"'+text.replace(/"/g,'""')+'"'; };
  const rows = [headers, ...filteredCases.map((item) => headers.map((key) => key === "issues" ? item.issues.join("; ") : item[key]))];
  const url=URL.createObjectURL(new Blob(["\ufeff"+rows.map((row)=>row.map(cell).join(",")).join("\r\n")],{type:"text/csv;charset=utf-8"}));
  const link=document.createElement("a");link.href=url;link.download=`rag-cases-run-${current.id}.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
refresh();
setInterval(() => { if(!document.hidden) refresh(); }, 5000);
document.addEventListener("visibilitychange", () => { if(!document.hidden) refresh(); });
window.addEventListener("resize", () => { if(current) renderTrend(); });
function updateNavigation() {
  for (const link of document.querySelectorAll(".sidebar nav a")) {
    if (link.hash === (location.hash || "#main")) link.setAttribute("aria-current", "location");
    else link.removeAttribute("aria-current");
  }
}
window.addEventListener("hashchange", updateNavigation);
updateNavigation();
