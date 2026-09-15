# Reliability Lab — terminal version

Run LLM evaluations and read the results directly in your terminal. Python 3.11+;
standard library only at runtime. No browser or web server is needed.

## Start here

From the project folder in PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m raglab.general_eval demo
```

For a fresh checkout, first run `python -m venv .venv`, activate it, and install
with `python -m pip install -e ".[dev]"`.

The demo uses reference answers, makes no model calls, and writes no result files.
Its scores check the evaluator, not an LLM. Results show task counts, domain scores,
repeated success, prompt robustness, and failures in plain text.

## Evaluate your own saved answers

Put one answer per line in JSONL, then score it locally without a model call:

```powershell
python -m raglab.saved_eval data/saved_answers.example.jsonl
python -m raglab.saved_eval my-answers.jsonl --output reports/my-answers.json
```

Each record needs `id`, `input`, `response`, `expected`, and `scorer`; `category`
is optional. Use `exact` for string equality, `numeric` for a response containing
only a number, `json` for parsed JSON value equality, or `valid_json` to check JSON
syntax (`expected` must be `null`). `json` ignores object key order, preserves array
order, and distinguishes booleans from numbers. `exact` is case- and
whitespace-sensitive. Numeric tolerance is absolute, defaults to zero, and can be
set with a non-negative `tolerance` field. `valid_json` does not check correctness
or a schema.

The included example deliberately has one failed exact match, so it prints useful
failure details and exits 1. Exit 0 means every case passed; exit 2 means the input
or command was invalid. `--output` writes the same case results and category counts
as JSON.

Generate fresh responses for any saved-evaluation JSONL file with the existing API
or subscription CLI adapters, then score the generated file offline:

```powershell
python -m raglab.saved_eval_generate data/extraction/tasks.jsonl --transport cli --provider codex --model gpt-5.6-sol --cli-version 0.154.0-alpha.6.2 --cli-executable codex --output reports/my-generated-answers.jsonl
python -m raglab.saved_eval reports/my-generated-answers.jsonl --output reports/my-generated-report.json
```

Generation makes one fresh request per case and sends the model only that case's
`input`, never its expected answer or scorer. The output refuses to overwrite an
existing file and preserves each raw answer, error, model configuration, public
request metadata, and adapter digest. Failed calls remain failed evaluation cases;
interrupted or truncated runs are rejected. A three-case Codex CLI check using
`gpt-5.6-sol` completed and scored 3/3; its
[inputs, provenance, and replay report](reports/extraction/generator-smoke/README.md)
are saved as workflow evidence, not a model ranking.

Compare two exported reports only when they cover the same cases and scoring setup:

```powershell
python -m raglab.saved_eval_compare reports/model-a.json reports/model-b.json
python -m raglab.saved_eval_compare reports/model-a.json reports/model-b.json --output reports/comparison.json
```

The command verifies matching IDs, inputs, expected values, scorers, categories,
and tolerances, then recomputes every score from the saved responses. It prints
overall and per-category changes plus named improvements, regressions, and shared
failures. Exit 0 means the candidate has no case-level regressions, exit 1 means it
has at least one regression, and exit 2 means an input or command is invalid.

### First document-extraction comparison

The [16-case extraction pack](data/extraction/tasks.jsonl) covers names, dates,
amounts, structured fields, and missing or conflicting information. Its empty
`response` fields are placeholders for your model's answers.

Live runs of Sol and Grok each passed **16/16**. Replay the comparison offline:

```powershell
python -m raglab.saved_eval_compare reports/extraction/2026-09-15/sol-report.json reports/extraction/2026-09-15/grok-report.json
```

This small custom sample checks the workflow; it does not rank the models.
[Results, methodology, and individual replay commands](reports/extraction/2026-09-15/README.md).

## See the saved model results

These commands replay existing responses offline; they need no API key:

```powershell
python -m raglab.general_eval evaluate --plan reports/general-eval/smoke-2026-09-15/codex-plan.json --generations reports/general-eval/smoke-2026-09-15/codex-generations.jsonl
python -m raglab.general_eval evaluate --plan reports/general-eval/smoke-2026-09-15/cursor-plan.json --generations reports/general-eval/smoke-2026-09-15/cursor-generations.jsonl
python -m raglab.general_eval_judge evaluate --plan reports/general-eval/smoke-2026-09-15/judge-plan.json --generations reports/general-eval/smoke-2026-09-15/judge-generations.jsonl
```

The saved Codex and Cursor runs each cover four base tasks and twelve attempts.
They are small workflow checks, not a general model ranking. The separate judge
run shows four false rejections across twenty-four presentations.

## Run a model

Existing API and subscription CLI adapters remain available. Choose your exact
model ID and configure its credential locally using the [API guide](docs/API_MODELS.md).
Freeze a small run, collect its responses, then display the scores:

```powershell
python -m raglab.general_eval freeze --transport api --provider openai --model MODEL_ID --items inst-05,reason-09,transform-08,fact-07 --samples 2 --output runs/model-plan.json
python -m raglab.general_eval generate --transport api --provider openai --model MODEL_ID --plan runs/model-plan.json --output runs/model-generations.jsonl
python -m raglab.general_eval evaluate --plan runs/model-plan.json --generations runs/model-generations.jsonl
```

Generation calls the selected model. The plan and raw response files preserve
what was asked and answered. Evaluation prints to the terminal; add
`--output runs/model-results.json` only when you want a JSON export. Exporting does
not create HTML or Markdown. See the [general evaluation guide](docs/GENERAL_LLM_EVALUATION.md)
for subscription CLI options, judge controls, and scoring limits.

## Other terminal commands

```powershell
python -m raglab.general_eval_judge demo
python -m raglab.testgen demo
python -m raglab.testgen evaluate --input reports/testgen/heldout.jsonl
python -m raglab evaluate
python -m pytest -q
```

The test-generation and RAG commands use `--report PATH.json` for optional JSON
exports. Software tests and model-quality scores are separate. The deterministic
RAG benchmark now answers all 41 answerable cases and abstains on all 15
unanswerable cases while preserving 89.0% required-phrase coverage. Its transparent
answer-type and conflict checks remain lexical heuristics; they cannot establish
semantic completeness for arbitrary paraphrases without a stronger inference model.

The dashboard, old HTML reports, and earlier work remain set aside in the
repository. They are not started or updated by the basic commands. The previous
web instructions are preserved in [README.web-archive.md](README.web-archive.md).
