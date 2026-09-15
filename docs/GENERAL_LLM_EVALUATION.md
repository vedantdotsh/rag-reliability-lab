# General LLM evaluation

The basic interface is the terminal. `python -m raglab.general_eval demo` and
`python -m raglab.general_eval_judge demo` show fixture results without writing files.
`evaluate` prints results directly; `--output PATH.json` is an optional JSON export.
No HTML reports are generated. The earlier dashboard and saved web reports remain
set aside. Real generation still saves a frozen plan and raw JSONL evidence.

This track measures prompt-only task success, repeatability, equivalent-prompt robustness, and
grader behavior without changing the existing RAG or test-generation benchmarks. The bundled pack
is an original, locally curated diagnostic: 60 base problems, 15 in each of instruction following,
short reasoning, structured transformation, and supplied-evidence factuality. Twenty base problems
have two manually equivalent prompt variants, producing 100 prompt variants in total. The pack is
not IFBench, LiveBench, SimpleQA, FACTS, or REFLECT, and its labels were code-audited locally rather
than human-validated.

Every candidate response must be one JSON object with `answer` and `disposition`. The graders keep
transport execution, answer disposition, formatting, constraint satisfaction, and correctness as
separate fields. Supplied-evidence questions include explicit abstention cases. Provider errors are
scored as failed attempts; requests skipped after a blocking response and local harness failures mark
the run incomplete and suppress reliability and paired-robustness summaries.

The default frozen schedule contains three fresh attempts for every prompt variant: 300 calls for one
system. Each record key is `(system, base_id, variant_id, condition, sample)`. The frozen plan records
the randomized sparse schedule, exact prompts, dataset, scorer, adapter, model, and transport
configuration. Output files use exclusive creation, and generation never retries or replaces a cell.

Offline replay also accepts the exact source-hash pairs recorded in
[`replay_compatibility.json`](../data/general_eval/replay_compatibility.json) for the verified runner
refactors, including the terminal presentation change. Every other plan field must still match.
A later source change requires another verified
compatibility entry; unknown hashes are rejected. Generation always requires a freshly matching plan.

Validate the local labels and constraints without a model:

```powershell
python -m raglab.general_eval validate
python -m raglab.general_eval_judge validate
```

Run deterministic fixture checks in the terminal:

```powershell
python -m raglab.general_eval demo
python -m raglab.general_eval_judge demo
```

For an API run, freeze first. Generation reads the credential only from the named environment
variable; the key is never placed in the plan or raw records.

```powershell
python -m raglab.general_eval freeze --transport api --provider openai --model MODEL_ID `
  --options '{"temperature":0.7,"max_output_tokens":512}' `
  --output reports/general-eval/openai-plan.json

python -m raglab.general_eval generate --transport api --provider openai --model MODEL_ID `
  --options '{"temperature":0.7,"max_output_tokens":512}' `
  --plan reports/general-eval/openai-plan.json `
  --output reports/general-eval/openai-generations.jsonl

python -m raglab.general_eval evaluate `
  --plan reports/general-eval/openai-plan.json `
  --generations reports/general-eval/openai-generations.jsonl `
  --output reports/general-eval/openai-report.json
```

For a subscription CLI run, record the actual CLI version and use the executable appropriate to the
provider. Sessions are fresh, prompt-only, and disqualified if a tool call is observed.

```powershell
python -m raglab.general_eval freeze --transport cli --provider codex --model gpt-5.6-sol `
  --cli-version VERSION --effort medium --output reports/general-eval/codex-plan.json

python -m raglab.general_eval generate --transport cli --provider codex --model gpt-5.6-sol `
  --cli-version VERSION --effort medium --cli-executable codex `
  --plan reports/general-eval/codex-plan.json `
  --output reports/general-eval/codex-generations.jsonl
```

Use `--items inst-05,reason-09,transform-08,fact-07 --samples 2` on `freeze` for the planned
12-call transport smoke. This subset is a workflow diagnostic, not a scored model ranking.

The report presents baseline macro success by domain so items with extra variants do not receive more
weight. Per-item repeated results include `pass^n`, the fraction of size-`n` subsets in which every
attempt passes, and `pass@n`, the chance that at least one size-`n` attempt passes. `pass^n` is the
reliability measure; `pass@n` describes retry opportunity. Equivalent-prompt changes are paired by
base problem and reported as variant-minus-baseline effects. Repeated calls do not add independent
task diversity, so this diagnostic track does not report a trial-flattened confidence interval or an
aggregate intelligence score.

The judge-control pack contains 12 author-written pairs: clean versus corrupted answers and clean
versus equivalent answers. Each pair is presented in both A/B orders. The deterministic validation
command proves that clean and equivalent answers pass the task grader and that corruptions fail it.
An optional real-model judge uses the same API or subscription adapters:

```powershell
python -m raglab.general_eval_judge freeze --transport cli --provider cursor `
  --model cursor-grok-4.6-xhigh --cli-version VERSION `
  --output reports/general-eval/cursor-judge-plan.json

python -m raglab.general_eval_judge generate --transport cli --provider cursor `
  --model cursor-grok-4.6-xhigh --cli-version VERSION `
  --cli-executable C:\Users\patil\AppData\Local\cursor-agent\agent.ps1 `
  --plan reports/general-eval/cursor-judge-plan.json `
  --output reports/general-eval/cursor-judge-generations.jsonl

python -m raglab.general_eval_judge evaluate `
  --plan reports/general-eval/cursor-judge-plan.json `
  --generations reports/general-eval/cursor-judge-generations.jsonl `
  --output reports/general-eval/cursor-judge-report.json
```

Judge errors are excluded from false-accept, false-reject, and order-flip calculations and retain an
explicit denominator. Judge results never enter candidate task scores.

The neutral-prefix parameter added to the shared subscription runner changes that adapter file's
hash. Historical test-generation JSONL remains offline-replayable, but an older frozen generation plan
correctly cannot authorize new calls with the changed adapter. Freeze a new plan for every new run.

## Subscription smoke results — 15 September 2026

The first live smoke used only 4 of the 60 base problems: one problem from each domain. Those four
problems produced 6 prompt variants and were run twice, for 12 candidate calls per system. This is a
transport and scoring diagnostic, not a model ranking or evidence about the full pack.

Both `gpt-5.6-sol` through the Codex subscription CLI and `cursor-grok-4.6-xhigh` through the Cursor
subscription CLI completed all 12 calls. Each had 12/12 correct trials, no provider or harness errors,
no invalid responses, and 100% baseline macro success on the four sampled problems. The one base
problem with equivalent prompt variants had a mean robustness change of 0.0 percentage points for
both systems. A perfect result on four deliberately small checks does not distinguish the systems or
predict their performance on the remaining 56 problems.

The separate `gpt-5.6-sol` judge run completed all 24 presentations of the 12 fixed control pairs. It
classified all 12 clean-versus-corrupted presentations correctly but falsely rejected equivalence on
4 of 12 clean-versus-equivalent presentations, for 20/24 scheduled success (83.33%). The failures were
the accepted case alias (`Oak tower` / `Oak Tower`) and accepted prefix alias (`West` /
`Warehouse West`), in both presentation orders. There were no order flips. This small control result
shows why judge validation is kept separate from candidate task scores: the judge preferred one valid
wording even though the deterministic task contract accepted both.

The immutable plans, raw JSONL, JSON reports, and archived HTML reports are in
[`reports/general-eval/smoke-2026-09-15`](../reports/general-eval/smoke-2026-09-15).
The frozen plan's `dataset_sha256` identifies the complete 60-problem pack used to validate and
select tasks. A candidate report's `dataset_sha256` identifies the evaluated task subset represented
in that report; both smoke reports therefore share the same four-task subset hash. The plan and report
hashes answer different provenance questions and should be retained together.
Replay all three reports offline into new output paths with:

```powershell
New-Item -ItemType Directory -Force reports/general-eval/replay | Out-Null

python -m raglab.general_eval evaluate `
  --plan reports/general-eval/smoke-2026-09-15/codex-plan.json `
  --generations reports/general-eval/smoke-2026-09-15/codex-generations.jsonl `
  --output reports/general-eval/replay/codex-report.json

python -m raglab.general_eval evaluate `
  --plan reports/general-eval/smoke-2026-09-15/cursor-plan.json `
  --generations reports/general-eval/smoke-2026-09-15/cursor-generations.jsonl `
  --output reports/general-eval/replay/cursor-report.json

python -m raglab.general_eval_judge evaluate `
  --plan reports/general-eval/smoke-2026-09-15/judge-plan.json `
  --generations reports/general-eval/smoke-2026-09-15/judge-generations.jsonl `
  --output reports/general-eval/replay/judge-report.json
```

The candidate plans record Codex CLI `0.154.0-alpha.6.2` at medium reasoning effort and Cursor CLI
`2026.09.10-fd3934a` with the selected Extra High model variant. Subscription CLIs may add hidden
scaffolding and use provider defaults, so these are system-configuration observations rather than
isolated base-model measurements.
