# Model comparison

Completed: 9 subscription model runs, 288 independent prompts. 32 further Cursor catalog entries were blocked by its exhausted Other Models allowance; they have no score. Qwen is the earlier local baseline.

[Study and evidence index](README.md)

Descriptive results on the same synthetic tasks. Provider defaults, native JSON constraints, tokenizers, reasoning budgets and hardware may differ. See each run's settings; these scores do not isolate model capability or establish a general ranking. All generation failures remain in the score denominator. No cost estimates are inferred.

| Provider / model | Prompt | Bugs caught | Score | Valid suites | Wrong assertions | Other failures | Median seconds | Input / output tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| codex / gpt-5.6-sol | code_only | 29/32 | 90.6% | 16/16 | 0 | 0 | 9.604 | 194034 / 2226 |
| codex / gpt-5.6-sol | code_docs | 30/32 | 93.8% | 16/16 | 0 | 0 | 9.077 | 194754 / 1953 |
| codex / gpt-6-astra | code_only | 28/32 | 87.5% | 15/16 | 0 | 1 | 10.154 | 208950 / 2135 |
| codex / gpt-6-astra | code_docs | 30/32 | 93.8% | 15/16 | 0 | 1 | 10.722 | 209392 / 2069 |
| cursor / cursor-grok-4.5-medium | code_only | 27/32 | 84.4% | 16/16 | 0 | 0 | 21.025 | 243994 / 13109 |
| cursor / cursor-grok-4.5-medium | code_docs | 30/32 | 93.8% | 16/16 | 0 | 0 | 20.333 | 241856 / 13756 |
| codex / gpt-5.6-terra | code_only | 28/32 | 87.5% | 16/16 | 0 | 0 | 7.322 | 194112 / 1318 |
| codex / gpt-5.6-terra | code_docs | 28/32 | 87.5% | 16/16 | 0 | 0 | 6.56 | 194948 / 1603 |
| codex / gpt-5.6-luna | code_only | 26/32 | 81.2% | 15/16 | 1 | 0 | 9.544 | 169130 / 3513 |
| codex / gpt-5.6-luna | code_docs | 30/32 | 93.8% | 16/16 | 0 | 0 | 8.264 | 169854 / 3545 |
| cursor / cursor-grok-4.6-xhigh | code_only | 27/32 | 84.4% | 16/16 | 0 | 0 | 38.575 | 246957 / 31197 |
| cursor / cursor-grok-4.6-xhigh | code_docs | 29/32 | 90.6% | 16/16 | 0 | 0 | 35.934 | 247465 / 33995 |
| codex / gpt-5.5 | code_only | 27/32 | 84.4% | 16/16 | 0 | 0 | 8.404 | 175988 / 3901 |
| codex / gpt-5.5 | code_docs | 28/32 | 87.5% | 16/16 | 0 | 0 | 8.091 | 176464 / 4110 |
| cursor / composer-2.5 | code_only | 25/32 | 78.1% | 15/16 | 0 | 1 | 16.277 | 230106 / 22751 |
| cursor / composer-2.5 | code_docs | 27/32 | 84.4% | 16/16 | 0 | 0 | 15.521 | 232983 / 20890 |
| codex / gpt-5.3-codex-spark | code_only | 20/32 | 62.5% | 12/16 | 1 | 3 | 6.03 | 139708 / 18366 |
| codex / gpt-5.3-codex-spark | code_docs | 24/32 | 75.0% | 14/16 | 0 | 2 | 5.502 | 140226 / 19528 |
| ollama / qwen2.5-coder:3b | code_only | 12/32 | 37.5% | 9/16 | 7 | 0 | 9.558 | 5298 / 1784 |
| ollama / qwen2.5-coder:3b | code_docs | 12/32 | 37.5% | 8/16 | 8 | 0 | 9.066 | 5803 / 1886 |

Full run settings and replayed evidence are in the companion JSON.
