# LLM test-generation benchmark

**Local LLM run — exploratory results, not an estimate of general capability.**

Model: `llama3.1:8b`
Scope: 2/24 tasks; splits: dev.
Dataset SHA-256: `354a0ea1ccef60d607e51a78413acbf28f1c22c188dc985ef8d85c6348312d6b`

| Prompt | Bugs caught / total | Score | Valid suites | False alarms | Invalid | Generation errors | Execution errors | Median generation seconds | Input / output tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| code_only | 0/4 | 0.0% | 0/2 | 1 | 0 | 1 | 0 | 39.434 | None / None |
| code_docs | 0/4 | 0.0% | 0/2 | 0 | 2 | 0 | 0 | 79.153 | 460 / 392 |

A suite earns bug-detection credit only after every assertion passes the correct implementation. Invalid suites and false alarms earn zero. Execution errors/timeouts never count as kills; all seeded mutants remain in the denominator.

Small synthetic dataset; one generation per task and condition. Fixed seed is best-effort. Timings include local load/queue overhead; code-only runs first in each pair. These results do not establish a statistically reliable prompt advantage.

## Paired scores

| Task | Documentation minus code-only score |
|---|---:|
| clamp | +0.0% |
| slug | +0.0% |
