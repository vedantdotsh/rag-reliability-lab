# Benchmark currency and next steps

Primary sources checked **10 September 2026**. This is a selection of relevant benchmarks, not an exhaustive claim about the newest paper.

## What is actually running here

The included 56 questions and 12 documents are a custom, synthetic support regression suite. They exercise the evaluator, retrieval, exact-source answering, missing evidence and conflicts. They are not an imported public benchmark. BM25 is the reproducible lexical baseline; phrase coverage and exact-source faithfulness are deliberately limited scoring heuristics. A fresh run date does not turn these into semantic correctness measurements or a state-of-the-art RAG evaluation.

Keep this suite as a fast smoke test. Add a separately versioned public dataset for broader evidence; do not replace it merely because another dataset is newer, and do not average scores from different suites together. The dashboard already restricts comparisons and trends to identical data/label fingerprints and report schemas.

## Public options relevant to this project

| Benchmark | Verified source and status | What it adds | Integration requirement |
|---|---|---|---|
| **T²-RAGBench** | [EACL 2026 paper](https://aclanthology.org/2026.eacl-long.8/); [authors' repository](https://github.com/uhh-hcds/g4kmu-paper) | The published version contains 23,088 question/context/answer triples. It evaluates retrieval from text-and-table documents followed by numerical reasoning. The authors identify 7,318 financial reports. | Preserve document/table structure, retrieve across the intended corpus, and score numeric/reference answers. An extractive two-sentence baseline and required substrings cannot evaluate derived numerical answers fairly. |
| **LIT-RAGBench** | [LREC 2026 paper](https://aclanthology.org/2026.lrec-1.427/); [authors' repository](https://github.com/Koki-Itai/LIT-RAGBench) | Generator-focused integration, reasoning, logic, table and abstention cases with supplied positive/negative chunks. The [revised paper](https://arxiv.org/abs/2603.06198v2) describes 114 Japanese questions plus an English version produced with translation and human curation. | Treat this as generation given context, not an end-to-end retrieval leaderboard. Its supplied workflow uses an LLM judge; record judge/model/prompt versions and check a human-reviewed sample before relying on scores. |
| **RAGBench** | [Galileo dataset card](https://huggingface.co/datasets/galileo-ai/ragbench); [original paper](https://arxiv.org/abs/2407.11005) | Broader question/document/response examples across 12 subsets, with sentence-support information and relevance, utilization and completeness labels. | Useful for evaluating or calibrating a scorer. Existing labelled responses and per-question contexts should not be treated as a ready-made global retrieval corpus. Preserve the supplied split and annotation provenance. |
| **FRAMES** | [Google dataset card](https://huggingface.co/datasets/google/frames-benchmark); [NAACL 2025 paper](https://aclanthology.org/2025.naacl-long.243/) | 824 multi-hop questions requiring evidence from 2–15 Wikipedia articles, including numerical, temporal and tabular reasoning. | Snapshot the source articles for reproducibility and score the reference answer. Fetching today's Wikipedia pages can change the evidence; the current three-document/two-sentence configuration is too restrictive for many cases. |

Dates and versions matter. T²-RAGBench's original [June 2025 preprint](https://arxiv.org/abs/2506.12071v1) describes 32,908 triples, while its final EACL paper and current author repository specify 23,088. Pin the exact dataset revision and split used; do not mix those counts or claim results against a version that was not evaluated. LIT-RAGBench also has a 2026 conference publication, so describing it only as a new preprint would now be incomplete.

## Recommended next addition

**T²-RAGBench is the strongest next fit for an analyst portfolio**: the task requires both finding evidence and interpreting numeric/table content. This is a project recommendation based on its documented task, not a claim that it is universally the best RAG benchmark.

Start with a fixed, clearly named pilot subset and its required corpus. Record the upstream revision, split, selection seed, source IDs and license/attribution metadata. Preserve a held-out set for evaluation rather than choosing cases that make the baseline pass. Report retrieval and answer correctness separately, with numeric tolerances and units where appropriate. Only label full-benchmark results as such after using the published full protocol; a small pilot is not a leaderboard submission.

Then use LIT-RAGBench to assess abstention and generator reasoning once a real generator is connected. RAGBench can help check whether a semantic scorer agrees with annotated evidence. The present literal scorers must remain labelled as literal, even if an LLM judge is later added alongside them.

No external benchmark dataset, judge, paid model call or new evaluation framework was installed or run during the dashboard work. This document and the dashboard's benchmark notes describe additions to consider, not completed benchmark results.
