# LLM test-generation benchmark

**Local LLM run — exploratory results, not an estimate of general capability.**

Model: `qwen2.5-coder:3b`
Scope: 8/24 tasks; splits: dev.
Dataset SHA-256: `354a0ea1ccef60d607e51a78413acbf28f1c22c188dc985ef8d85c6348312d6b`

Protocol: `testgen-v4`

| Prompt | Bugs caught / total | Score | Valid suites | False alarms | Invalid | Generation errors | Execution errors | Median generation seconds | Input / output tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| code_only | 6/16 | 37.5% | 7/8 | 1 | 0 | 0 | 0 | 12.642 | 2472 / 937 |
| code_docs | 7/16 | 43.8% | 5/8 | 3 | 0 | 0 | 0 | 9.284 | 2691 / 892 |

A suite earns bug-detection credit only after every assertion passes the correct implementation. Invalid suites and false alarms earn zero. Execution errors/timeouts never count as kills; all seeded mutants remain in the denominator.

Small synthetic dataset; one generation per task and condition. Fixed seed is best-effort. Timings include local load/queue overhead; code-only runs first in each pair. These results do not establish a statistically reliable prompt advantage.

Mean paired documentation difference: +6.2%. 95% task-bootstrap interval: +0.0% to +18.8%. This resamples tasks, not repeated model generations.

## Paired scores

| Task | Documentation minus code-only score |
|---|---:|
| boolean | +50.0% |
| chunks | +0.0% |
| clamp | +0.0% |
| lower-median | +0.0% |
| overlap-count | +0.0% |
| page | +0.0% |
| slug | +0.0% |
| unique | +0.0% |
