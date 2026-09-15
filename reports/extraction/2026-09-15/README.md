# Document extraction: first live comparison

Run date: 15 September 2026. Sixteen fictional document cases, authored locally.
Both models answered all sixteen correctly under the stated checks.

| Category | Sol | Grok |
|---|---:|---:|
| Names | 3/3 | 3/3 |
| Dates | 3/3 | 3/3 |
| Amounts | 3/3 | 3/3 |
| Structured fields | 3/3 | 3/3 |
| Missing or conflicting information | 4/4 | 4/4 |
| **Total** | **16/16** | **16/16** |

No improvements, regressions, or shared failures in this run. This small, relatively
easy custom sample checks the workflow; it does not establish model equivalence,
general reliability, or a ranking. The cases were frozen before generation and
were not made harder after seeing the results.

## Replay in the terminal

From the repository folder, after activating its Python environment:

```powershell
python -m raglab.saved_eval reports/extraction/2026-09-15/sol-answers.jsonl
python -m raglab.saved_eval reports/extraction/2026-09-15/grok-answers.jsonl
python -m raglab.saved_eval_compare reports/extraction/2026-09-15/sol-report.json reports/extraction/2026-09-15/grok-report.json
```

These commands make no model calls. The comparison recomputes scores rather than
trusting the saved pass/fail flags. It requires matching test definitions.

## What ran

- Codex CLI `0.154.0-alpha.6.2`, requested model `gpt-5.6-sol`, medium reasoning.
  The CLI did not return a separate model identifier; the requested ID is recorded.
- Cursor CLI `2026.09.10-fd3934a`, requested model `cursor-grok-4.6-xhigh`;
  returned model label `Cursor Grok 4.6 Extra High`, ask mode.
- One batch of sixteen cases per model, one sample per case, no retries of a
  completed generation. Cases within a batch share context and are not independent
  model sessions. Each provider adds its own system instructions and defaults.
- Both received the same [user prompt](prompt.txt) content, containing only case IDs
  and inputs. Codex received LF line endings; Cursor received Windows CRLF. The
  manifest hashes normalized LF content and also records the actual file hash.
  Expected answers and scoring definitions were withheld. Fresh empty
  working directories were used; no tool calls were observed. The Cursor workspace
  needed its normal trust flag before generation could start.
- Responses were unpacked from the required ID-to-string JSON object without
  changing individual answer strings. JSON field comparisons ignore object key
  order, preserve array order, and distinguish booleans from numbers. Numeric
  tolerances and reference answers are visible in [the frozen cases](tasks.jsonl).

## Files

- `*-generation.json`: raw final answer and public execution/usage metadata.
- `*-answers.jsonl`: individual answers joined to the frozen test definitions.
- `*-report.json`: scored cases, failures, and category summaries.
- [comparison.json](comparison.json): recomputed side-by-side results.
- [manifest.json](manifest.json): dataset, prompt, scorer, and artifact hashes.

The editable pack is [data/extraction/tasks.jsonl](../../../data/extraction/tasks.jsonl).
Its empty `response` fields are placeholders. Copy it, replace those fields with
actual model answers, evaluate each copy with `--output`, then compare the reports.
Names and document details are fictional. This pack is not a public benchmark.
