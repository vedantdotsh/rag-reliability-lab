# LLM test-generation benchmark

**Local LLM run — exploratory results, not an estimate of general capability.**

Model: `llama3.1:8b`
Scope: 2/24 tasks; splits: dev.
Dataset SHA-256: `354a0ea1ccef60d607e51a78413acbf28f1c22c188dc985ef8d85c6348312d6b`

Protocol: `testgen-v3`

| Prompt | Bugs caught / total | Score | Valid suites | False alarms | Invalid | Generation errors | Execution errors | Median generation seconds | Input / output tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| code_only | 0/4 | 0.0% | 0/2 | 2 | 0 | 0 | 0 | 15.885 | 977 / 214 |
| code_docs | 2/4 | 50.0% | 1/2 | 1 | 0 | 0 | 0 | 17.401 | 1026 / 248 |

A suite earns bug-detection credit only after every assertion passes the correct implementation. Invalid suites and false alarms earn zero. Execution errors/timeouts never count as kills; all seeded mutants remain in the denominator.

Small synthetic dataset; one generation per task and condition. Fixed seed is best-effort. Timings include local load/queue overhead; code-only runs first in each pair. These results do not establish a statistically reliable prompt advantage.

Mean paired documentation difference: +50.0%. 95% task-bootstrap interval: +0.0% to +100.0%. This resamples tasks, not repeated model generations.

## Paired scores

| Task | Documentation minus code-only score |
|---|---:|
| clamp | +0.0% |
| slug | +100.0% |
