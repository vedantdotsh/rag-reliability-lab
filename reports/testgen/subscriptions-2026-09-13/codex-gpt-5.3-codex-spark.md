# LLM test-generation benchmark

**LLM run — exploratory results, not an estimate of general capability.**

Model: `gpt-5.3-codex-spark`
Scope: 16/24 tasks; splits: test.
Subscription CLI configuration: `{"cli_version": "codex-cli 0.154.0-alpha.6.2", "protocol": "cli-v1", "provider": "codex", "reasoning_effort": "medium", "sampling": "CLI defaults; no native output schema", "session": "fresh empty working directory; no resume", "timeout_seconds": 240, "tool_policy": "prompt prohibits tools; observed tool calls disqualify the suite"}`

CLI system prompts and defaults affect these results; remote weights are unverifiable.

Dataset SHA-256: `354a0ea1ccef60d607e51a78413acbf28f1c22c188dc985ef8d85c6348312d6b`

Protocol: `testgen-v4`

| Prompt | Bugs caught / total | Score | Valid suites | False alarms | Invalid | Generation errors | Execution errors | Median generation seconds | Input / output tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| code_only | 20/32 | 62.5% | 12/16 | 1 | 3 | 0 | 0 | 6.03 | 139708 / 18366 |
| code_docs | 24/32 | 75.0% | 14/16 | 0 | 2 | 0 | 0 | 5.502 | 140226 / 19528 |

A suite earns bug-detection credit only after every assertion passes the correct implementation. Invalid suites and false alarms earn zero. Execution errors/timeouts never count as kills; all seeded mutants remain in the denominator.

Small synthetic dataset; one generation per task and condition. Fixed seed is best-effort when supported. Timings include network/load/queue overhead; code-only runs first in each pair. These results do not establish a statistically reliable prompt advantage.

Mean paired documentation difference: +12.5%. 95% task-bootstrap interval: -6.2% to +34.4%. This resamples tasks, not repeated model generations.

## Paired scores

| Task | Documentation minus code-only score |
|---|---:|
| balanced-brackets | +50.0% |
| business-days | +0.0% |
| discount | +0.0% |
| flatten | +0.0% |
| interval | +0.0% |
| inventory | +50.0% |
| ipv4 | -50.0% |
| leap-year | -50.0% |
| luhn | +100.0% |
| merge-counts | +0.0% |
| percentile-rank | +0.0% |
| range-compression | +100.0% |
| rotate | +0.0% |
| run-length | +0.0% |
| transpose | +0.0% |
| version | +0.0% |
