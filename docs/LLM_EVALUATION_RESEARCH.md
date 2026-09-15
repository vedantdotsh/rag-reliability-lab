# Research on General LLM Evaluation Methods

The strongest direction for this project is a broader evaluation suite with separate measures for task success, instruction following, factuality, repeatability, robustness, and evaluator quality. The immediate opportunity is to combine verifiable tasks with repeated, recorded trials and a small test set for the graders themselves. This would support more credible comparisons across API models and subscription-based systems without requiring a new agent framework.

This report covers eighteen primary research papers and technical reports, emphasizing 2025–2026 work available by **15 September 2026**. It distinguishes published conference papers, workshop work, technical reports, and recent preprints. Recommendations are engineering judgments for the current repository; reported experimental findings belong to the cited studies. This is a selected synthesis of implementable methods, not an exhaustive systematic review or a new model leaderboard.

## Recommended direction

Build a separate, versioned general-evaluation track in three steps:

1. **Verifiable breadth:** instruction constraints, short reasoning problems, and structured data transformations with independently checked answers. IFBench and LiveBench supply useful approaches and reference implementations.[^4][^5]
2. **Reliability measurement:** repeated trials, paired prompt variants, explicit failure categories, and uncertainty estimates that respect the number of independent tasks.[^1][^2][^3]
3. **Evaluator validation:** human-checked original/corrupted answer pairs, judge error rates, and sensitivity checks before using model judgments as a primary score.[^13][^14][^17][^18]

Add factual question answering next. Long-context and interactive tool-agent evaluations are worthwhile later, once the required input handling, environments, and grading controls exist. A larger model catalog alone would leave most of the current measurement gaps unchanged.

The most useful distinctive experiment would be: **Does the apparent model ranking survive repeated runs, equivalent prompts, and a validated grader?** This is answerable, relevant beyond code generation, and small enough to implement incrementally.

## Research shortlist

“Adopt” means adopt the method in a local pilot, not claim replication of the full published benchmark. A named subset or adaptation must be reported as such. Publication status describes the source consulted; an arXiv listing alone is not evidence of peer review.

| Research | Date and status | Contribution relevant to evaluation | Implementation judgment |
|---|---|---|---|
| **Towards a Science of AI Agent Reliability**[^1] | February 2026; v3, 2 June; ICML 2026 acceptance stated by authors | Twelve metrics across consistency, robustness, predictability, and safety; experiments on 15 models and two agent benchmarks. | **Adopt selected measures.** Report success alongside consistency; an always-wrong system can be perfectly consistent. |
| **Expanding the AI Evaluation Toolbox with Statistical Models**[^2] | February 2026; NIST AI 800-3 technical report | Separates accuracy on a fixed benchmark from accuracy generalized to related items; analyzes repeated observations with statistical models. | **Adopt the design principles now.** Reserve mixed-effects analysis for a larger dataset and an offline analysis step. |
| **Don't Use the CLT in LLM Evals With Fewer Than a Few Hundred Datapoints**[^3] | ICML 2025 position paper | Shows poor small-sample uncertainty coverage in several common settings; examines score intervals and Bayesian alternatives. | **Adopt appropriate intervals.** No universal confidence-interval formula covers binary, paired, clustered, and continuous metrics. |
| **Generalizing Verifiable Instruction Following / IFBench**[^4] | NeurIPS 2025, Datasets and Benchmarks | Three hundred prompts with 58 new verifiable constraints; tests generalization beyond familiar constraint templates. | **Best first task pack.** Start with auditable constraints and distinguish constraint satisfaction from answer usefulness. |
| **LiveBench**[^5] | ICLR 2025 | Refreshed, objectively graded tasks across mathematics, coding, reasoning, language, instruction following, and data analysis. | **Adopt task and release practices.** Pin an available public release; do not equate a local subset with the live leaderboard. |
| **SimpleQA Verified**[^6] | 9 September 2025; arXiv technical paper | Curates 1,000 factual questions through deduplication, source reconciliation, and grading improvements. | **Add next.** Suitable for closed-book factuality, with attempted-answer and abstention reporting. |
| **The FACTS Leaderboard**[^7] | 11 December 2025; Google technical paper | Separates factuality into parametric knowledge, search, grounding, and multimodal tasks. | **Adopt the separation.** A citation-support score cannot stand in for all forms of factual accuracy. |
| **Flaw or Artifact? Rethinking Prompt Sensitivity in Evaluating LLMs**[^8] | EMNLP 2025 | Shows that answer extraction and grading can create apparent prompt sensitivity; validates semantic grading against human annotations. | **Adopt grader controls.** Test accepted aliases and numerical equivalence before attributing a score change to reasoning. |
| **SycoBench-600**[^9] | Findings of ACL, July 2026 | Measures misleading social pressure and acceptance of correct suggestions; 600 MCQ instances share 272 normalized stems. | **Good second robustness pack.** Preserve stem grouping and separate harmful answer changes from useful corrections. |
| **General Agent Evaluation / Exgentic**[^10] | February 2026; v2, 11 May; ICLR 2026 workshop | Crosses five architectures, five models, and six benchmarks through a common protocol. | **Adopt configuration reporting now.** Consider the external harness when real tool-agent tasks are needed. |
| **τ²-Bench**[^11] | June 2025; original arXiv paper and maintained implementation | Evaluates conversational agents where both the agent and simulated user can act on an environment. | **Later, separate execution track.** Requires state, tools, a user simulator, and outcome verification. |
| **LongBench Pro**[^12] | 6 January 2026; arXiv paper | Bilingual long-context tasks with context-dependency, length, difficulty, and task-specific metrics. | **Later, bounded subset.** Context length, truncation, reasoning budget, and grading must be explicit. |
| **Nine Judges, Two Effective Votes**[^13] | 28 May 2026; arXiv preprint; Apple research page in June | Finds strongly correlated errors in a nine-judge panel; majority voting provides little or negative benefit in the studied settings. | **Adopt the caution.** Measure panel value against a validated single judge and human labels. |
| **Bias and Uncertainty in LLM-as-a-Judge Estimation**[^14] | 7 May 2026; arXiv preprint | Explains bias correction, calibration uncertainty, and risks from sharing calibration across evaluated models. | **Adopt diagnostics before correction.** Check judge errors separately by candidate model and task type. |
| **Can We Trust LLM Judges**[^15] | 10 September 2026; recent arXiv preprint | Studies capability-dependent judging errors and weighted voting, including estimates based on inter-judge disagreement. | **Experimental only.** Consensus used as a proxy label can preserve common mistakes. |
| **Search-Time Contamination in Deep Research Agents**[^16] | 3 June 2026; arXiv preprint | Distinguishes benchmark metadata, question-context, and explicit-answer leakage during browsing. | **Adopt for future search tasks.** Record retrieved evidence and benchmark-artifact exposure. |
| **Time to REFLECT**[^17] | 18 May 2026; arXiv preprint | Uses controlled, validated errors in agent traces and reports to measure judge failure detection. | **Strong project fit.** Begin with verified answer mutations; full trajectory evaluation can follow. |
| **Judging LLM-as-a-Judge: Concerning Rubric Artifacts**[^18] | 31 August 2026; recent arXiv preprint | Investigates rubric-only predictive signals and whether judgments respond correctly to counterfactual edits. | **Add diagnostic cases.** Its domain and model scope do not justify declaring all rubric-based judges unreliable. |

## Interpretation of the evidence

### Reliability and statistical validity

Rabanser and colleagues distinguish reliability from average accuracy. Their consistency measure rewards both repeated success and repeated failure, and their overall aggregate excludes safety. Use the individual dimensions to expose different failure patterns; consistency alone cannot establish useful performance.[^1]

For this project, the recommended first measures are deliberately simpler than the complete paper: average task score across trials, fraction of tasks succeeding on every trial, and changes under paired perturbations. Trajectory similarity is not needed for a text-only pilot. Two correct solutions can legitimately follow different paths; rewarding identical trajectories would introduce an additional objective that requires justification.

The NIST report distinguishes repeat performance on fixed questions from generalization to a broader population. Its mixed-effects approach uses information about item difficulty, subject to assumptions about sampling, dimensionality, and model fit. Statistical precision cannot establish that a benchmark represents deployment traffic.[^2]

Bowyer and colleagues find small-sample undercoverage for normal and percentile bootstrap intervals in several settings. They discuss Wilson intervals for binary proportions and Bayesian alternatives. Check coverage for the intended design; their results do not invalidate every bootstrap or make Bayesian analysis assumption-free.[^3]

**Recommendation:** retain the current historical confidence intervals as part of the frozen result, explain their scope, and make the new track explicit about independent items, repeated trials, pairing, and its target population. More repetitions reduce some uncertainty about the sampled tasks; they do not create additional task diversity.

### Verifiable performance across domains

IFBench's central contribution is evaluating unfamiliar constraint types, with separate strict and loose scoring. Its limitations are useful: verifiable constraints can be artificial and do not cover every meaningful user instruction. The paper also discusses a tradeoff between fulfilling the underlying request and optimizing the constraint score.[^4]

A pilot should therefore report both whole-prompt constraint success and individual-constraint success. Include a task-validity check where the content permits one. For example, producing valid JSON is one requirement; returning the requested records with correct values is another. Passing the JSON parser alone must never earn credit for completing the data task.

LiveBench extends objective grading to several domains and uses refreshed material to reduce contamination exposure. Its published method remains useful even when a particular public dataset release is older than its leaderboard. Open-ended qualities without a well-defined answer remain outside the reach of its objective graders.[^5]

The practical starting set is instruction following, short reasoning with independently checked answers, and structured transformations. Use fresh problem instances where possible, but audit their answers before seeing candidate outputs. Keep task families separate in reports; an arbitrary mixture can make a single aggregate score change merely because the benchmark composition changed.

### Factuality and abstention

SimpleQA Verified illustrates that dataset repair and grading policy can matter as much as selecting a judge. It specifies question-dependent numerical tolerances and clearer treatment of hedged answers. The task measures knowledge recalled without tools; running the same questions with browsing answers a different evaluation question.[^6]

FACTS distinguishes closed-book recall, tool-supported search, supplied-context grounding, and image-related factuality. Its public/private split also means that a locally runnable public subset cannot reproduce the entire hosted evaluation. The paper's autoraters are measurement components with validation results, not perfect labels.[^7]

**Recommendation:** start with a separate closed-book factuality pack, then add a supplied-evidence pack. Report correct answers, wrong answers, and abstentions with their denominators. A system that answers very little may have high accuracy on attempted questions; that number should appear beside coverage, rather than replace overall performance.

For evidence-grounded answers, distinguish correctness of the final answer, support for each material claim, and coverage of the requested information. A response may copy a source faithfully while answering the wrong question. A source itself may also be incorrect. These require separate labels and, for disputed cases, human adjudication.

### Robustness and correction behavior

Hua and colleagues supply an important counterpoint to treating every prompt-dependent score change as model brittleness. Their experiments show that rigid extraction can reject semantically equivalent responses. They also find that well-designed mathematical equivalence checks can be stable without an LLM judge. Their human validation covers sampled outputs and does not establish universal judge reliability.[^8]

Consequently, maintain two explicit contracts. When exact structure is required by the task, malformed output is a real failure. When the task permits equivalent answers, the grader should accept declared aliases and valid equivalent forms. Neither contract should change after candidate results are inspected.

SycoBench adds a different kind of robustness: resisting misleading pressure while accepting useful correction. Its follow-up conditions share a baseline answer, and repeated question stems require grouped analysis. The controlled MCQ setting is helpful for attribution but is not a substitute for natural, extended dialogue.[^9]

**Recommendation:** begin with manually reviewed, meaning-preserving prompt variants. Add social-pressure and correct-suggestion conditions as a distinct experiment. Report the denominator for each conditional metric: a flip from correct to wrong is evaluated on initially correct answers; recovery after a correct suggestion concerns initially wrong answers. Do not reward a model merely for never changing its mind.

### Evaluation of model judges

Kohli's nine-judge study estimates roughly two effective independent votes in its NLI setting. The best individual judge is competitive with or better than the panel across the studied datasets. This is evidence against assuming independence from different model names, not a universal bound on every possible ensemble.[^13]

Fiedler shows why judge approval rate differs from true correctness, and why a calibration set cannot automatically be reused across candidate models. Bias correction becomes unstable when the judge provides weak information; calibration uncertainty must also enter uncertainty estimates. The proposed diagnostics deserve attention before implementing an automatic corrected leaderboard.[^14]

The newest selected paper, Zhang and colleagues' 10 September preprint, presents encouraging weighted-voting results, including a simulated shift between task mixtures. Its disagreement estimator treats the other judges' majority as a proxy for truth. That creates a clear tension with the correlated-error evidence: a shared mistake can look like reliable agreement. The reported near-oracle result is relative to that study's voting oracle and setting, not proof of general label-free validity.[^15]

REFLECT introduces localized defects into screened executions and tests whether judges detect the degradation. Automated filters and human validation check the intended defect and unintended changes. Controlled mutations still need a complementary sample of naturally occurring errors.[^17]

Bagaria and colleagues test whether verdicts respond to changes in criterion satisfaction. Their rubric-only associations do not demonstrate causally that judges ignore answers, and their counterfactual experiments cover limited models and domains. The diagnostic is useful while broader claims remain preliminary.[^18]

**Recommendation:** before introducing open-ended grading, create a small held-out set of clean answers and verified corruptions. Include wrong entities or quantities, unsupported claims, missing requested information, and incorrect citations. Add equivalent correct rewrites as negative controls: a judge should detect factual degradation without penalizing harmless paraphrases.

Blind candidate identity, balance pair order, and keep judge prompts and versions fixed. Measure false acceptance of corrupted answers, false rejection of clean answers, and changes under order reversal. Validate on all pairs, not only those where two judges disagree; unanimous mistakes would otherwise escape review. Keep calibration examples separate from the final judge test set, grouped by original answer.

### Tools, context, and contamination

General Agent Evaluation finds that architecture affects outcomes and failure patterns even with the same backbone model. Its fully crossed design is more informative than comparing one model inside one application with another model inside a different application. Its workshop study is still bounded by particular agents, tasks, budgets, and relatively uncertain per-benchmark estimates.[^10]

For GPT-versus-Cursor comparisons, the practical unit is **model plus application scaffold plus settings plus budget**. A subscription application's hidden prompt, tool policy, routing, or reasoning setting may prevent strict model-only isolation. Report such results as system comparisons; use a common direct-API configuration when the research question specifically concerns model differences.

τ²-Bench evaluates stateful cooperation and uses repeated-trial success measures. It requires more than generating a syntactically correct tool call: the task involves the user, environment state, and policy. Its maintained repository documents a July 2026 grading change for `banking_knowledge`; scores across that boundary are not comparable for that domain, while other domains are unaffected.[^11][^21]

LongBench Pro measures several kinds of long-context work rather than one retrieval trick. Its reported protocol includes different generation budgets and explicit truncation for inputs exceeding a model's context. Those choices matter when interpreting results. A local adaptation should record original and delivered input lengths and keep truncated-input results distinguishable.[^12]

Search-time contamination is separate from training contamination. Wang and colleagues analyze benchmark-related material encountered during browsing. Their detection is imperfect and their comparative analysis includes assumptions about item difficulty, so reported associations should not be treated as universal causal estimates of score inflation.[^16]

**Recommendation:** use fixed evidence snapshots for an initial retrieval or grounding extension. For later open-web tests, retain URLs, content snapshots where permitted, tool observations, and known benchmark-artifact matches. A match should trigger inspection rather than automatic exclusion: retrieving legitimate factual evidence is part of the task. Fresh publication dates and private test questions reduce some exposure but do not establish contamination-free evaluation.

## Measurement specification for a pilot

The following is a proposed local protocol, not a reproduction of any single paper. Freeze it before generating scored outputs.

### Units and outcomes

Use `base_item_id` for the underlying problem, `variant_id` for a controlled prompt version, `sample_id` for a repeated trial, and `system_id` for a fully specified model/application configuration. Within a frozen manifest, the logical key is `(system_id, base_item_id, variant_id, condition, sample_id)`; include manifest identity when combining studies. Trial independence requires appropriate fresh sessions and state; a new ID alone does not establish it. All variants of one problem belong in the same development or test split.

Each attempted trial records the exact request, raw visible response, provider metadata, elapsed time, and declared generation settings. Store execution status, response disposition, and task score separately: a completed response may answer, abstain, refuse, or violate the required format. Correct abstention can earn credit when the task explicitly tests it. Provider failures and timeouts count against system success under a declared policy; verified harness faults remain recorded and make the affected comparison cell incomplete until resolved. They must not be attributed to the model or silently removed to improve its score.

Predeclare retries. If retrying is part of the evaluated product, retain every attempt and charge its resources to that task. For a single-attempt model experiment, a failed attempt stays failed. An interrupted run can resume unattempted record keys; it must not replace inconvenient completed answers.

### Metrics

| Measure | Definition and interpretation |
|---|---|
| Mean task performance | Average repeated scores within each variant, then apply declared variant and base-item weights. Report family-level results before any overall aggregate. |
| Repeated success | For each variant, measure success on all specified trials; average with predeclared equal weights within each base item and then across base items. Keep baseline and perturbation conditions separately visible. |
| Prompt robustness | Compute each base item's difference between baseline and variant trial means before aggregating. An all-variants-pass measure is separate and must be predeclared. Matching sample numbers do not imply shared provider randomness. |
| Factual accuracy and coverage | Correct answers / all questions; attempted answers / all questions; correct answers / attempted answers. Show invalid and failed calls separately from deliberate abstention. |
| Confidence quality | Only for a protocol that collects confidence: mean squared error between stated probability and correctness (Brier score), plus error versus coverage when low-confidence answers are withheld. |
| Grader quality | False acceptance, false rejection, and sensitivity to controlled defects, with independent reference labels and clear uncertainty. |
| Resources | Observed input/output usage where provided, wall-clock latency, and all attempts. Monetary cost only from verified applicable prices or billing records; missing usage remains missing. |

For binary outcomes, distinguish **pass@k**, at least one success among k attempts, from **pass^k**, success on all k attempts. With n exchangeable trials containing c successes, the corresponding subset estimators are:

```text
pass@k = 1 - choose(n - c, k) / choose(n, k)
pass^k =     choose(c, k)     / choose(n, k)
```

Here `1 <= k <= n`, and `choose(a, k) = 0` when `a < k`. Compute per task before aggregating. For example, four successes in five trials gives pass@2 = 1 and pass^2 = 0.6. The first represents opportunity with retries and an ability to recognize success; it is not ordinary single-attempt reliability. A model that simply produces valid output has not necessarily satisfied the task-success criterion.[^11]

Do not recover these metrics from one response per task, or interpret a code-only response and a code-plus-documentation response as two repetitions of the same condition. Do not obtain confidence labels retrospectively from a different model and call them the evaluated model's confidence.

### Uncertainty and comparisons

The analysis unit must follow the data structure. Questions sharing a source passage, problem stem, or synthetic template may be correlated. Preserve pairing across compared systems and group related variants together. Report counts of distinct problems and families as well as total calls.

For a genuinely independent binary proportion, a Wilson interval is a simple descriptive option. Repeated-trial averages, mutation fractions, paired differences, and calibrated judge estimates require methods appropriate to those quantities. In a larger study, compare task-cluster resampling with a suitable hierarchical statistical model and check interval coverage under plausible simulated data. Avoid treating a bootstrap label as proof of valid uncertainty.

For the initial small pilot, prioritize effect sizes, paired outcomes, and failure inspection. Do not declare a general winner from close scores. Define primary comparisons in advance; dozens of post-hoc model, domain, and prompt comparisons create opportunities to select accidental differences. Use a fixed collection budget initially. If adaptive stopping is later introduced, use an analysis valid for that stopping rule.

## Integration with the current repository

The implementation assessment refers to local commit `d820650` on `codex/llm-test-generation-benchmark`. This report adds research documentation; the proposed general-evaluation features have not been implemented or measured.

The repository currently has two narrower tracks: a synthetic support-document RAG evaluation and a test-generation benchmark. The latter contains 24 functions and 48 seeded mutants, with 16 functions and 32 mutants in its test split. Its September subscription comparison contains nine usable systems, each evaluated with one response for each of two conditions on those 16 functions. These results characterize that task and protocol, not general LLM capability.

| Existing component | Verified boundary | Smallest useful extension |
|---|---|---|
| [API transport](<C:/Users/patil/OneDrive/Documents/ChatGPT/improv/rag-reliability-lab/src/raglab/testgen_api.py:71>) | Accepts a text prompt, builds provider-specific requests, and normalizes visible text and usage. | Import the existing transport for the new track. No provider framework is needed merely to send another kind of prompt. |
| [CLI generation](<C:/Users/patil/OneDrive/Documents/ChatGPT/improv/rag-reliability-lab/src/raglab/testgen_cli.py:101>) | The exported path prepends a test-generation-specific prefix and enforces a no-tools session. | Add a narrow full-prompt entry point for subscription evaluation; retain the old wrapper's behavior and record a new adapter hash for new plans. |
| [Frozen test-generation plan](<C:/Users/patil/OneDrive/Documents/ChatGPT/improv/rag-reliability-lab/src/raglab/testgen.py:261>) | Records one generation per task/condition and hashes prompts, schema, scorer, worker, and settings. | Give the new pack its own manifest, protocol version, record keys, and verifier hashes. |
| [Test-generation evaluator](<C:/Users/patil/OneDrive/Documents/ChatGPT/improv/rag-reliability-lab/src/raglab/testgen.py:385>) | Rejects duplicate task/condition pairs and scores a four-test suite against seeded mutants. | Use separate task-type verifiers; do not bypass duplicate validation to insert repetitions. |
| [Current uncertainty calculation](<C:/Users/patil/OneDrive/Documents/ChatGPT/improv/rag-reliability-lab/src/raglab/testgen.py:206>) | Resamples paired task deltas; explicitly does not estimate generation variance. | Collect repeated observations first, then add an analysis matching the new experimental design. |
| [RAG metrics](<C:/Users/patil/OneDrive/Documents/ChatGPT/improv/rag-reliability-lab/src/raglab/metrics.py:1>) | Lexical answer checks, citation checks, and an extractive source-support heuristic. | Add a separately named semantic evaluation only after reference-label and judge validation. |
| [Comparison reports](<C:/Users/patil/OneDrive/Documents/ChatGPT/improv/rag-reliability-lab/src/raglab/testgen_compare.py:8>) | Require compatible benchmark scope and do not infer unavailable cost. | Retain those rules; add domain, sample count, variant, grader, and system-configuration disclosures. |

Historical raw responses support replay and inspection. They do not support new claims about run-to-run variation, pass@k, confidence calibration, factuality, or judge accuracy. Their latency also includes application and network effects, and condition order was not randomized. A new experiment is required to answer those questions.

The frozen plan hashes the entire CLI adapter file. Editing that file therefore prevents an old plan from authorizing new or continued generation, even if the original wrapper behaves identically. Historical offline replay can retain its behavior, but exact source provenance remains the old hash and commit. Keep that revision available; new generation uses a new manifest. Use a separate general CLI module if preserving the adapter file byte-for-byte is required.

The no-tools CLI restriction is appropriate for the present benchmark. Actual agent evaluation would require a distinct runner with reproducible starting state, permitted tools, event capture, resets, resource limits, and final-state assertions. Removing the existing guard would not produce a valid tool-use benchmark.

### Implementation priorities and acceptance criteria

The order below reflects value and dependency, not a promise of measured performance gains. Effort estimates are rough engineering estimates for this repository and exclude model runtime, dataset annotation, and access delays.

| Priority | Deliverable | Completion criteria | Rough effort |
|---|---|---|---|
| **1 — Verifiable general pack** | Separate JSONL pack, API runner, neutral no-tools CLI path, deterministic graders, replayable report | Correct and incorrect fixtures verify each scoring rule; invalid outputs and failed calls remain visible; API and subscription paths preserve exact prompts and identify their provenance. | 2–4 working days |
| **2 — Repeated and perturbed trials** | New trial IDs, randomized recorded schedule, grouped metrics | Completeness checked against a frozen manifest; no overwritten trials; variants stay with their base item; numerical checks cover known all-pass, all-fail, and mixed outcomes. | 1–3 days after priority 1 |
| **3 — Grader validation** | Clean/corrupted/equivalent answer cases and optional model-judge runner | Reference labels independently checked; calibration/test origins disjoint; error rates and order sensitivity reported; no judge score silently merged into objective scores. | 2–4 days plus annotation |
| **4 — Factuality and selective answering** | Closed-book QA, then supplied-context QA | Source-backed gold, explicit aliases/tolerances, attempted-answer labels, coverage, and any confidence protocol fixed before evaluation. | 2–4 days plus curation |
| **5 — Long-context and tool-agent evaluation** | Bounded external benchmark adapters | Input/truncation accounting for long context; isolated state and deterministic outcome assertions for agents; upstream release and settings recorded. | Separate scoping exercise |

Use the current standard-library approach for manifests, transport, JSONL results, and simple graders. A framework becomes useful when maintaining distinct agent environments or complex scoring integrations costs more than adopting a proven external harness. Evaluate that decision against concrete needs, including raw-artifact export and offline replay.

## Pilot design and collection budget

Start with **60 independently reviewed base problems**: 20 instruction-following, 20 short reasoning, and 20 structured transformations. Include easy controls and difficult cases. For related templates, record the higher-level family so that nominal item count does not conceal dependence.

Select three available system configurations for the pilot, then expand once the pipeline and labels are sound. Subscription configurations require the neutral CLI path in priority 1. Where access permits, vary provider/model family; running only closely related models limits the range of observed behavior. Recheck model availability and usable quota at collection time. An installed catalog entry or existing API key does not establish that a model is callable.

| Collection component | Planned calls |
|---|---:|
| 3 systems × 60 base problems × 3 baseline trials | 540 |
| 3 systems × 20 selected base problems × 2 additional prompt variants × 3 trials | 360 |
| **Candidate-model pilot total** | **900** |
| Optional judge study: 80 clean/corrupted pairs × 2 presentation orders × 2 judges | 320 |

Each candidate system sees 100 prompt variants: 60 baselines plus 40 additional variants, each repeated three times. The optional judge study uses separately curated pairs; it is not automatically produced by the candidate-model pilot. Human annotation and adjudication are additional work. Include equivalent rewrites and natural errors in a subsequent extension, with their added call count declared before collection.

These are call counts, not monetary estimates. Token lengths, reasoning usage, judge input length, retries, provider pricing, and subscription accounting determine actual cost and duration. Use a few unscored development cases to measure request sizes and validate access before freezing the scored run. Keep development results out of the final pilot.

Three trials expose conspicuous instability but give coarse per-item success estimates. Sixty base problems, especially only twenty per family, make this a diagnostic pilot rather than a definitive ranking study. If the pilot works, increase the number and diversity of base items before spending most of the budget on repeated runs of the same small set.

For an illustrative follow-up, nine systems × 300 base problems × three trials requires **8,100 baseline calls**, before perturbations or judging. A study seeking a specific detectable difference needs sample planning using pilot variability and pairing, rather than choosing 300 as a universal sufficiency threshold.

## Data access, releases, and limits

IFBench provides code and data, but the licenses differ: its repository identifies Apache 2.0 for code and ODC-BY-1.0 for data, with additional use guidance and third-party model-output terms. Its full requirements include NLP packages such as NLTK and spaCy. A small dependency-free adaptation is feasible only for selected constraints, and must carry a distinct subset/adaptation label.[^19]

LiveBench's repository exposes a release selector and warns that some newer questions are not public. Its coding track also has substantial container requirements. Record the exact public release and task IDs actually obtained; the repository's access notes are more relevant to feasibility than assuming that every hosted leaderboard task is downloadable.[^20]

τ²-Bench's evolving task and grading releases reinforce the need for separate dataset, environment, and grader hashes.[^21] For other candidate datasets, confirm downloadable artifacts, redistribution terms, and required assets before importing them. This report establishes methodological relevance; it does not certify every benchmark as a ready-to-run local dependency.

The research leaves several boundaries clear. Benchmark results do not establish broad occupational competence or deployment safety. Prompt-only evaluation does not measure autonomous tool use. English or English/Chinese tests do not establish multilingual quality generally. New preprints may change after review, and public benchmark exposure remains difficult to rule out for opaque training corpora.

The proposed project contribution is therefore a reproducible evaluation method and an honest account of its evidence: which tasks were tested, which systems and budgets were used, which failures occurred, how graders were checked, and which conclusions remain uncertain.

## Sources

The numbered references below give the original sources used for the findings and implementation assessment. Dates distinguish paper publication from later repository or research-page updates. Sections cited are those relevant to the methods and limitations discussed above.

[^1]: Stephan Rabanser, Sayash Kapoor, Peter Kirgis, Kangheng Liu, Saiteja Utpala, and Arvind Narayanan. [Towards a Science of AI Agent Reliability](https://arxiv.org/html/2602.16666v3). First posted 18 February 2026; version 3, 2 June 2026. Authors report ICML 2026 acceptance. Sections 3–6 and Table 2.

[^2]: Drew Keller, Kweku Kwegyir-Aggrey, Ryan Steed, Anita K. Rao, Julia L. Sharp, and A. Stevie Bergman. [Expanding the AI Evaluation Toolbox with Statistical Models](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.800-3.pdf). NIST AI 800-3, February 2026. DOI: 10.6028/NIST.AI.800-3. Sections 3–4 and 6.2.

[^3]: Sam Bowyer, Laurence Aitchison, and Desi R. Ivanova. [Position: Don't Use the CLT in LLM Evals With Fewer Than a Few Hundred Datapoints](https://proceedings.mlr.press/v267/bowyer25a.html). ICML 2025, PMLR 267. [Full text](https://arxiv.org/html/2503.01747). Sections 3.1–3.5 and appendices on interval methods.

[^4]: Valentina Pyatkin and colleagues. [Generalizing Verifiable Instruction Following](https://proceedings.neurips.cc/paper_files/paper/2025/hash/46499a0622ecf568b72d17b61e45dbd5-Abstract-Datasets_and_Benchmarks_Track.html). NeurIPS 2025, Datasets and Benchmarks Track. First arXiv posting 3 July 2025. [Full text](https://arxiv.org/html/2507.02833), Sections 2, 5, and 7.

[^5]: Colin White and colleagues. [LiveBench: A Challenging, Contamination-Limited LLM Benchmark](https://proceedings.iclr.cc/paper_files/paper/2025/file/e4a46394ba5378b3f9a186a5b4c650d1-Paper-Conference.pdf). ICLR 2025. Use the conference title; the repository retains the earlier “Contamination-Free” wording. Sections on construction, reproducibility, and limitations.

[^6]: Lukas Haas, Gal Yona, Giovanni D'Antonio, Sasha Goldshtein, and Dipanjan Das. [SimpleQA Verified: A Reliable Factuality Benchmark to Measure Parametric Knowledge](https://arxiv.org/html/2509.07968). 9 September 2025. Sections 2–4, including source reconciliation, numerical tolerance, and hedging policy.

[^7]: Aileen Cheng, Alon Jacovi, Amir Globerson, and colleagues. [The FACTS Leaderboard: A Comprehensive Benchmark for Large Language Model Factuality](https://storage.googleapis.com/deepmind-media/FACTS/FACTS_benchmark_suite_paper.pdf). Google, 11 December 2025. Sections 2–7. A later leaderboard refresh is not a new paper publication date.

[^8]: Andong Hua, Kenan Tang, Chenhe Gu, Jindong Gu, Eric Wong, and Yao Qin. [Flaw or Artifact? Rethinking Prompt Sensitivity in Evaluating LLMs](https://aclanthology.org/2025.emnlp-main.1006/). EMNLP, November 2025, pp. 19889–19899. [Paper](https://aclanthology.org/2025.emnlp-main.1006.pdf), Sections 2–4 and limitations.

[^9]: Debu Sinha. [SycoBench-600: Measuring Sycophancy and Correction Selectivity in LLM Assistants](https://aclanthology.org/2026.findings-acl.1759/). Findings of ACL, July 2026, pp. 35278–35284. [Paper](https://aclanthology.org/2026.findings-acl.1759.pdf), Sections 3–4.

[^10]: Elron Bandel and colleagues. [General Agent Evaluation](https://arxiv.org/html/2602.22953v2). First posted 26 February 2026; version 2, 11 May 2026. Presented at the ICLR 2026 Workshop on Agents in the Wild. Sections 3–6 and reproducibility appendices. [Project](https://www.exgentic.ai/).

[^11]: Victor Barres, Honghua Dong, Soham Ray, Xujie Si, and Karthik Narasimhan. [τ²-Bench: Evaluating Conversational Agents in a Dual-Control Environment](https://arxiv.org/html/2506.07982). June 2025. Sections 3–4; original agent/user environment and repeated-success evaluation.

[^12]: Ziyang Chen, Xing Wu, Junlong Jia, Chaochen Gao, Qi Fu, Debing Zhang, and Songlin Hu. [LongBench Pro: A More Realistic and Comprehensive Bilingual Long-Context Evaluation Benchmark](https://arxiv.org/html/2601.02872). First posted 6 January 2026. Sections 2–5, especially inference settings and truncation in Section 5.1.

[^13]: Guneet Kohli. [Nine Judges, Two Effective Votes: Correlated Errors Undermine LLM Evaluation Panels](https://arxiv.org/html/2605.29800v1). 28 May 2026, preprint. Sections 3–4. [Apple research page](https://machinelearning.apple.com/research/correlated-llm-evaluation-panels), published June 2026.

[^14]: James Fiedler. [Bias and Uncertainty in LLM-as-a-Judge Estimation](https://arxiv.org/html/2605.06939). 7 May 2026, preprint. Sections 3–4, including judge-invariance assumptions and calibration diagnostics.

[^15]: Gemma Zhang, Prachi Badarayani, Asmi Kumar, Sadid Hasan, and Sulaiman Vesal. [Can We Trust LLM Judges: A Study of Capability-Dependent Biases and Multi-Judge Ensemble for Bias Calibration](https://arxiv.org/html/2609.12002v1). 10 September 2026, preprint. Sections 4–6, especially the disagreement-based estimator and task-drift experiment.

[^16]: Yongjie Wang, Xinyue Zhang, Kunhong Yao, Zhiwei Zeng, Kaisong Song, Jun Lin, and Zhiqi Shen. [Search-Time Contamination in Deep Research Agents: Measuring Performance Inflation in Public Benchmark Evaluation](https://arxiv.org/html/2606.05241). 3 June 2026, preprint. Sections 3–5 and limitations.

[^17]: Leyao Wang, Yanan He, Peng Chen, Asaf Yehudai, Yixin Liu, Rex Ying, Michal Shmueli-Scheuer, and Arman Cohan. [Time to REFLECT: Can We Trust LLM Judges for Evidence-based Research Agents?](https://arxiv.org/html/2605.19196). 18 May 2026, preprint. Section 2.2 on controlled interventions and validation; Section 3 and limitations.

[^18]: Anshul Bagaria, Sowmya S Sundaram, Gokul S Krishnan, and Balaraman Ravindran. [Judging LLM-as-a-Judge: Concerning Rubric Artifacts in LLM-based Automated Text Generation Evaluation](https://arxiv.org/html/2609.02942). First posted 31 August 2026, preprint. Sections 5 and 7. The identifier begins with 2609, but the displayed first-submission date is August.

[^19]: Allen Institute for AI. [IFBench repository](https://github.com/allenai/IFBench), README licensing and evaluation instructions; [requirements](https://raw.githubusercontent.com/allenai/IFBench/main/requirements.txt). Accessed 15 September 2026. Code and data licensing statements are separate.

[^20]: LiveBench authors. [LiveBench repository](https://github.com/LiveBench/LiveBench), README sections on running evaluations, public-release availability, and coding environments. Accessed 15 September 2026. Repository defaults and access notes may lag the hosted leaderboard.

[^21]: Sierra Research. [τ²-Bench repository README](https://github.com/sierra-research/tau2-bench/blob/main/README.md). Accessed 15 September 2026. July 2026 v1.0.1 notice specifies the `banking_knowledge` grading boundary and preservation of prior behavior through a pinned tag.
