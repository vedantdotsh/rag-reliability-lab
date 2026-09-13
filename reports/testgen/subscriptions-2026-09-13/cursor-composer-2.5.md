# LLM test-generation benchmark

**LLM run — exploratory results, not an estimate of general capability.**

Model: `composer-2.5`
Scope: 16/24 tasks; splits: test.
Subscription CLI configuration: `{"cli_version": "2026.09.10-fd3934a", "protocol": "cli-v1", "provider": "cursor", "reasoning_effort": "selected model variant", "sampling": "CLI defaults; no native output schema", "session": "fresh empty working directory; no resume", "timeout_seconds": 240, "tool_policy": "prompt prohibits tools; observed tool calls disqualify the suite"}`

CLI system prompts and defaults affect these results; remote weights are unverifiable.

Dataset SHA-256: `354a0ea1ccef60d607e51a78413acbf28f1c22c188dc985ef8d85c6348312d6b`

Protocol: `testgen-v4`

| Prompt | Bugs caught / total | Score | Valid suites | False alarms | Invalid | Generation errors | Execution errors | Median generation seconds | Input / output tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| code_only | 25/32 | 78.1% | 15/16 | 0 | 1 | 0 | 0 | 16.277 | 230106 / 22751 |
| code_docs | 27/32 | 84.4% | 16/16 | 0 | 0 | 0 | 0 | 15.521 | 232983 / 20890 |

A suite earns bug-detection credit only after every assertion passes the correct implementation. Invalid suites and false alarms earn zero. Execution errors/timeouts never count as kills; all seeded mutants remain in the denominator.

Small synthetic dataset; one generation per task and condition. Fixed seed is best-effort when supported. Timings include network/load/queue overhead; code-only runs first in each pair. These results do not establish a statistically reliable prompt advantage.

Mean paired documentation difference: +6.2%. 95% task-bootstrap interval: -12.5% to +25.1%. This resamples tasks, not repeated model generations.

## Paired scores

| Task | Documentation minus code-only score |
|---|---:|
| balanced-brackets | -50.0% |
| business-days | +0.0% |
| discount | +0.0% |
| flatten | +0.0% |
| interval | +0.0% |
| inventory | +0.0% |
| ipv4 | +0.0% |
| leap-year | -50.0% |
| luhn | -50.0% |
| merge-counts | +100.0% |
| percentile-rank | +50.0% |
| range-compression | +50.0% |
| rotate | +0.0% |
| run-length | +0.0% |
| transpose | +0.0% |
| version | +50.0% |
