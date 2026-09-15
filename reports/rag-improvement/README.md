# RAG evidence checks: before and after

The same 56-case custom benchmark and unchanged quality thresholds were used for
both saved reports. The fix adds requested-detail checks and abstains on numeric
conflicts between equally scoped source statements. It does not read expected
answers, case IDs, or abstention labels at answer time.

| Measurement | Before | After |
|---|---:|---:|
| Answerable questions answered | 41/41 | 41/41 |
| Unanswerable questions correctly declined | 2/15 | 15/15 |
| Required-phrase coverage | 89.02% | 89.02% |
| Citation correctness | 100% | 100% |
| Exact-source faithfulness | 100% | 100% |
| Quality gate | Fail | Pass |

From the repository root:

```powershell
python -m raglab compare reports/rag-improvement/before.json reports/rag-improvement/after.json --max-drop 0
python -m raglab evaluate --gate
```

The gate checks aggregates; passing does not mean every answer contains all
required phrases. The two-sentence extractor still has incomplete multi-source
answers. These lexical rules catch explicit missing detail, numbered-entity
mismatches, and matching-scope numeric conflicts, but do not prove semantic
completeness across arbitrary wording, source precedence, or paraphrased conflicts.

Fresh regression tests also distinguish severity numbers from response times,
plan-specific retention from conflicting limits, dates from phone numbers, and
maintenance dates from storage regions. Historical baseline reports are preserved.
