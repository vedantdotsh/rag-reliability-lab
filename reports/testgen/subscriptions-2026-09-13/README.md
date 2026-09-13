# Codex and Cursor model evaluation — 13 September 2026

**Nine models completed 288 independent generation prompts through existing subscription logins.** The catalog contained 41 provider/model entries. The other 32 Cursor entries were blocked by the exhausted Other Models allowance, with on-demand spending disabled. They were not sent generation requests and have no measured score.

[Open the HTML comparison](comparison.html) · [Detailed table](comparison.md) · [Catalog snapshot](inventory.json) · [Availability](availability.json) · [Reproduction and methodology](../../../docs/SUBSCRIPTION_BENCHMARK.md)

Each condition uses 16 public synthetic functions with 32 seeded bugs. A generated suite must contain exactly four tests and pass the correct function before receiving bug-detection credit. One sample per task and condition; no repairs, retries or selection of better outputs. The original Qwen run is included below as a historical baseline.

| Model through CLI | Code only: bugs caught | Code + docs: bugs caught | Valid suites: code / docs | Wrong assertions: code / docs | Format errors: code / docs |
|---|---:|---:|---:|---:|---:|
| [codex / gpt-5.6-sol](codex-gpt-5.6-sol.html) | 29/32 (90.6%) | 30/32 (93.8%) | 16/16 / 16/16 | 0 / 0 | 0 / 0 |
| [codex / gpt-6-astra](codex-gpt-6-astra.html) | 28/32 (87.5%) | 30/32 (93.8%) | 15/16 / 15/16 | 0 / 0 | 1 / 1 |
| [cursor / cursor-grok-4.5-medium](cursor-cursor-grok-4.5-medium.html) | 27/32 (84.4%) | 30/32 (93.8%) | 16/16 / 16/16 | 0 / 0 | 0 / 0 |
| [codex / gpt-5.6-terra](codex-gpt-5.6-terra.html) | 28/32 (87.5%) | 28/32 (87.5%) | 16/16 / 16/16 | 0 / 0 | 0 / 0 |
| [codex / gpt-5.6-luna](codex-gpt-5.6-luna.html) | 26/32 (81.2%) | 30/32 (93.8%) | 15/16 / 16/16 | 1 / 0 | 0 / 0 |
| [cursor / cursor-grok-4.6-xhigh](cursor-cursor-grok-4.6-xhigh.html) | 27/32 (84.4%) | 29/32 (90.6%) | 16/16 / 16/16 | 0 / 0 | 0 / 0 |
| [codex / gpt-5.5](codex-gpt-5.5.html) | 27/32 (84.4%) | 28/32 (87.5%) | 16/16 / 16/16 | 0 / 0 | 0 / 0 |
| [cursor / composer-2.5](cursor-composer-2.5.html) | 25/32 (78.1%) | 27/32 (84.4%) | 15/16 / 16/16 | 0 / 0 | 1 / 0 |
| [codex / gpt-5.3-codex-spark](codex-gpt-5.3-codex-spark.html) | 20/32 (62.5%) | 24/32 (75.0%) | 12/16 / 14/16 | 1 / 0 | 3 / 2 |
| [ollama / qwen2.5-coder:3b (historical)](../heldout.html) | 12/32 (37.5%) | 12/32 (37.5%) | 9/16 / 8/16 | 7 / 8 | 0 / 0 |

Rows are ordered by total bugs caught across the two conditions; this is a descriptive ordering on this dataset, not a general model ranking. A wrong assertion means at least one test failed on the correct function, so that entire suite receives zero credit. Format errors likewise receive zero. All nine new runs had zero transport/generation errors and zero evaluator execution errors.

## Interpretation

Documentation changes both test selection and answer validity. The paired task-bootstrap intervals and individual failures are retained in each report. These intervals resample the 16 functions; they do not measure variation across repeated model generations. The public split had already been inspected in the earlier experiment, so these runs are an extension on known tasks rather than new unseen evaluation evidence.

Codex ran each GPT model at medium reasoning. Cursor selected one standard-speed variant per family: Composer 2.5, Grok 4.5 medium and Grok 4.6 Extra High. The CLI system context, reasoning budgets and output handling differ; this comparison evaluates the configured CLI experience. Token counts include CLI context, and elapsed time includes process startup, networking and concurrent scheduling. No price estimates or controlled speed claims are made.

## Evidence and verification

- Each model has a frozen plan JSON, 32 original responses in JSONL, and replayed JSON, Markdown and HTML reports. Click its name above for expandable evidence.
- All nine frozen plans match the implemented protocol at commit c6b62ba. Every saved report exactly matches offline replay of its original responses.
- Software validation: 106 tests passed; Ruff and whitespace checks passed. The historical Qwen report replays byte for byte without changing its results.
- Two one-prompt development transport pilots (Astra and Grok 4.6) preceded the full study. They are excluded from the 288 benchmark prompts and all scores.
- Only visible final answers and public response metadata are saved; CLI reasoning text and echoed environment messages are discarded. Observed tool calls disqualify a suite. No direct API keys were used.

## Cursor entries blocked by quota

The following are the selected family representatives from the saved catalog. Availability was classified from the account spending dashboard, not inferred from failed generations. Auto, Fast duplicates and extra reasoning variants are not separate benchmark models.

- `gpt-5.3-codex`
- `gpt-5.2`
- `claude-opus-5-medium`
- `gpt-5.6-sol-medium`
- `claude-fable-5-medium`
- `gemini-3.7-flash-medium`
- `claude-sonnet-5-medium`
- `gpt-5.6-luna-medium`
- `claude-opus-4-8-medium`
- `gpt-5.5-medium`
- `claude-fable-5-1-medium`
- `gemini-3.8-flash-medium`
- `muse-spark-1.3-medium`
- `gpt-5.6-terra-medium`
- `claude-4.6-sonnet-medium`
- `claude-opus-4-7-medium`
- `gpt-5.4-medium`
- `claude-4.6-opus-high`
- `claude-4.5-opus-high`
- `gemini-3.6-flash-medium`
- `gemini-3.1-pro`
- `gpt-5.4-mini-medium`
- `gpt-5.4-nano-medium`
- `claude-4.5-sonnet`
- `gpt-5.1`
- `gemini-3-flash`
- `gemini-3.5-flash`
- `claude-4-sonnet`
- `gpt-5-mini`
- `kimi-k3-high`
- `kimi-k2.7-code`
- `glm-5.2-high`
