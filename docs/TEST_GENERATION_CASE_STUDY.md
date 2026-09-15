# Measuring the reliability of LLM-generated tests

**Completed 13 September 2026.** In the frozen held-out experiment, both prompt
conditions detected **12 of 32 seeded bugs (37.5%)**. Adding documentation produced
no overall mutation-score gain. [Open the evidence viewer](../reports/testgen/heldout.html)
or read the [machine-readable report](../reports/testgen/heldout.json).

| Held-out measurement | Code only | Code + documentation |
|---|---:|---:|
| Functions / generated suites | 16 | 16 |
| Credited bugs found | 12/32 | 12/32 |
| Suites passing every assertion | 9/16 | 8/16 |
| Suites with wrong assertions | 7 | 8 |
| Format / provider / execution errors | 0 / 0 / 0 | 0 / 0 / 0 |
| Median generation time (diagnostic) | 9.558 s | 9.066 s |
| Provider-reported input / output tokens | 5,298 / 1,784 | 5,803 / 1,886 |

The mean paired difference was **0 percentage points**, with a 95% task-bootstrap
interval of **-18.75 to +12.5 points**. Documentation won on two functions,
code-only won on one, and thirteen tied. This does not support a general claim
that documentation improves generated tests.

Documentation caught one additional bug each on `leap-year` and `rotate`, but lost
two on `version`. For example, adding year 400 to the leap-year tests exposed a
century-boundary bug missed by the code-only suite.

A concrete failure appears in `version`: the documentation condition asserted
that `"1.0"` sorts after `"1"`, while the implementation correctly treats them as
equal. One wrong assertion disqualified the whole suite. Well-formed JSON alone
did not make its tests reliable.

All 32 final responses were generated once after the plan was saved. Offline
replay reproduced the saved report exactly; the frozen configuration and all
generation timestamps were verified. The repository's **52 software tests pass**.

## Research question

Does adding a function's documentation help a local LLM generate tests that are
both correct and able to detect bugs? A test that fails is not automatically
useful: it may contain the wrong expected answer.

This is a small software-engineering experiment using 24 author-written Python
functions, each with two deliberately seeded bugs. Eight functions form the
development set; sixteen form the final held-out set. The dataset, prompts,
raw outputs and scoring implementation are available in this repository.

## Design

Each function receives two independent prompts: source code alone, and the same
code plus its documentation. Each prompt requests four tests. Neither receives
the reference assertions, seeded bugs or the other condition's response.

The model generates bounded JSON arguments and assertions. The runner executes
trusted dataset code in isolated Python processes. It never executes model-written
Python. A suite receives mutation credit only if all of its assertions first pass
the correct implementation. Every selected mutant remains in the denominator,
including when generation fails. A timeout is never a detected bug.

The final plan fixes the model digest, runtime version, inference settings,
task IDs and dataset, prompt, schema and scoring-code hashes before generation.
There is one generation per task and condition, with no retries on final outputs.

## What development uncovered

The initial Llama 3.1 runs produced malformed tests and incorrect expected values.
Development also uncovered two defects in the experiment's integration:

1. Empty JSON schemas were interpreted as objects by the local grammar backend.
   Enumerating JSON types corrected that mistake in protocol v3.
2. Ollama 0.20.7 ignored Qwen 3.5's output schema when thinking was disabled.
   A constant-schema probe returned Markdown fences. Updating the existing runtime
   to 0.34.0 applied the [upstream correction](https://github.com/ollama/ollama/pull/15901).
   A subsequent [probe](../reports/testgen/schema-probe-034.json) requested a value
   conflicting with the schema and correctly received the schema's permitted value.

Earlier attempts are preserved. They are development diagnostics, and the broken
runtime attempt does not measure performance under the intended constraints.
The small model still produced semantic errors after formatting was repaired.
The [plain-JSON diagnostic](../reports/testgen/json-format-diagnostic.json)
reproduced representative errors with the broad schema removed. A separate
[thinking-mode probe](../reports/testgen/thinking-diagnostic.json) consumed the
1,536-token budget without producing test data. These probes use development
functions only and are not paired benchmark scores.

The final configuration is selected from complete eight-function development
runs on the corrected runtime, using mean credited mutation score across both
prompt conditions. Ties favor more valid suites, then lower median latency.
These development comparisons are model-and-prompt selection, not a general
model leaderboard. Final outputs do not influence that choice.

| Development configuration | Code only | Code + documentation |
|---|---:|---:|
| Llama 3.1 8B, v3, Ollama 0.20.7 | 0/16 | 3/16 |
| Llama 3.1 8B, v4, Ollama 0.20.7 | 2/16 | 1/16 |
| Qwen 3.5 4B, v4, Ollama 0.20.7 (schema ignored) | 0/16 | 0/16 |
| Qwen 3.5 4B, v4, Ollama 0.34.0 | 1/16 | 1/16 |
| Qwen 3.5 4B, v3, Ollama 0.34.0 | 4/16 | 4/16 |
| Qwen 2.5 Coder 3B, v4, Ollama 0.34.0 | 6/16 | 7/16 |

Each entry is credited bugs out of all sixteen selected development mutants.
Development measurements cannot estimate unseen-task performance.

**Selected:** `qwen2.5-coder:3b`, protocol `testgen-v4`, Ollama 0.34.0.
Its mean development mutation score was 40.625%, with 12/16 valid suites and
no format/provider/execution errors. The [frozen plan](../reports/testgen/heldout-plan.json)
was saved before any held-out generation. Its SHA-256 is
`9ab313c1913d96c1a1b8f2e965f7fa173e9d1d8a4397928c2d5fc830ff590d5c`.

## What the evidence can support

This project demonstrates reproducible experiment design, mutation testing,
failure analysis, local LLM integration and an evidence viewer. The paired
task-bootstrap interval describes variation across these sixteen functions;
it does not account for repeated-generation variability. The synthetic tasks
and two selected bugs per function cannot establish real-repository performance,
absence of training contamination or broad model superiority.

Exact JSON representations are compared, including integer/float distinctions.
Code-only requests run first in each pair. Latency includes local loading and
queueing, so timing differences are diagnostic and are not a controlled speed
comparison. The updated runtime used CPU inference on this Windows laptop after
GPU discovery failed; no GPU speed claim is made.

## Relevance to the SAP application

SAP's [LLM-based software-engineering research position, requisition 459240](https://jobs.sap.com/job/Walldorf-InternThesisWorking-Student-%28fmd%29-Evaluating-and-Improving-LLM-based-SE-Solutions-in-SAP-HANA-69190/1427816733/)
lists test generation, benchmarking and software reliability among its example
tasks, and asks applicants to demonstrate programming and LLM experience through
projects. This experiment provides a concrete artifact to discuss in that context.
It does not use SAP code, integrate with HANA or establish performance on HANA.

## Implementation and review

The project was developed with AI coding assistance. GPT-6 Astra coordinated,
integrated and tested the implementation; GPT-5.3-Codex-Spark reviewed the worker
and experiment checks; Cursor Grok 4.6 Extra High supplied a read-only report-view
proposal that Astra reviewed and simplified. The implementation uses Python's
standard library and native HTML disclosure controls, with no added runtime
dependencies. The benchmarked models are separate from these coding assistants.

See [the reproduction guide](TEST_GENERATION.md) for commands and execution limits.

## CV bullet draft

Developed an AI-assisted Python benchmark for LLM test generation across 24
functions and 48 seeded bugs; implemented paired prompt evaluation, strict
assertion validation, a frozen held-out experiment, offline replay and CI reporting.

## Post draft

I built a small experiment around a practical question: does giving an LLM a
function's documentation help it generate better tests?

On sixteen held-out functions, Qwen2.5-Coder 3B detected 12 of 32 seeded bugs
(37.5%) with either prompt. Documentation showed no overall gain, and wrong
assertions disqualified 7/16 code-only suites and 8/16 documentation suites.

The difficult part was deciding what counts as a good test. A failing assertion
can expose a bug, but it can also contain an invented expected answer. My runner
checks every generated assertion against the correct implementation before
giving the suite credit for finding seeded bugs.

The project includes 24 Python functions, 48 seeded bugs, separate development
and held-out sets, raw model responses, a frozen experiment plan and an offline
report where you can inspect each assertion. Development also exposed an Ollama
structured-output integration bug, which I verified and corrected with the
official runtime update.

The case study reports the measured results and their limits. This was built
with AI coding assistance, documented in the repository.
