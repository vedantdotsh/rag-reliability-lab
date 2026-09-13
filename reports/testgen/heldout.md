# LLM test-generation benchmark

**Local LLM run — exploratory results, not an estimate of general capability.**

Model: `qwen2.5-coder:3b`
Scope: 16/24 tasks; splits: test.
Dataset SHA-256: `354a0ea1ccef60d607e51a78413acbf28f1c22c188dc985ef8d85c6348312d6b`

Protocol: `testgen-v4`

| Prompt | Bugs caught / total | Score | Valid suites | False alarms | Invalid | Generation errors | Execution errors | Median generation seconds | Input / output tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| code_only | 12/32 | 37.5% | 9/16 | 7 | 0 | 0 | 0 | 9.558 | 5298 / 1784 |
| code_docs | 12/32 | 37.5% | 8/16 | 8 | 0 | 0 | 0 | 9.066 | 5803 / 1886 |

A suite earns bug-detection credit only after every assertion passes the correct implementation. Invalid suites and false alarms earn zero. Execution errors/timeouts never count as kills; all seeded mutants remain in the denominator.

Small synthetic dataset; one generation per task and condition. Fixed seed is best-effort. Timings include local load/queue overhead; code-only runs first in each pair. These results do not establish a statistically reliable prompt advantage.

Mean paired documentation difference: +0.0%. 95% task-bootstrap interval: -18.8% to +12.5%. This resamples tasks, not repeated model generations.

## Paired scores

| Task | Documentation minus code-only score |
|---|---:|
| balanced-brackets | +0.0% |
| business-days | +0.0% |
| discount | +0.0% |
| flatten | +0.0% |
| interval | +0.0% |
| inventory | +0.0% |
| ipv4 | +0.0% |
| leap-year | +50.0% |
| luhn | +0.0% |
| merge-counts | +0.0% |
| percentile-rank | +0.0% |
| range-compression | +0.0% |
| rotate | +50.0% |
| run-length | +0.0% |
| transpose | +0.0% |
| version | -100.0% |
