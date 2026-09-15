# Custom-case generation smoke test

Three independent requests through the reusable generator, using Codex CLI
`0.154.0-alpha.6.2`, requested model `gpt-5.6-sol`, medium reasoning.
All three completed and passed: a German-formatted amount, a structured item
array, and a missing due date. This validates the command, not general model quality.

Each model session received only its case input and the prompt-only instruction.
The expected answers remained local. The CLI did not return a separate model ID;
the requested model and observed execution metadata are in `sol-answers.jsonl`.

From the repository root, replay without a model call:

```powershell
python -m raglab.saved_eval reports/extraction/generator-smoke/sol-answers.jsonl
```

To generate a new run through an installed Codex CLI (consumes subscription usage):

```powershell
python -m raglab.saved_eval_generate reports/extraction/generator-smoke/cases.jsonl --transport cli --provider codex --model gpt-5.6-sol --cli-version YOUR_INSTALLED_VERSION --cli-executable codex --output runs/extraction-new.jsonl
python -m raglab.saved_eval runs/extraction-new.jsonl --output runs/extraction-new-report.json
python -m raglab.saved_eval_compare reports/extraction/generator-smoke/sol-report.json runs/extraction-new-report.json
```

Choose a new output path for each generation. Existing files are never overwritten.
