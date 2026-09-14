# LLM Test Generation Benchmark

This project measures whether documentation helps an LLM generate correct tests
that detect bugs. It contains 24 author-written Python functions and 48 seeded
bugs: 8 development tasks and 16 tasks reserved for the final experiment.

## See and replay results

The recorded experiment uses Qwen2.5-Coder 3B, protocol v4 and Ollama 0.34.0:
[HTML viewer](../reports/testgen/heldout.html),
[result summary](../reports/testgen/heldout.md),
[raw generations](../reports/testgen/heldout.jsonl),
[frozen plan](../reports/testgen/heldout-plan.json), and
[case study with CV/post drafts](TEST_GENERATION_CASE_STUDY.md).

Open a generated HTML report directly in a browser. Expand **Inspect evidence**
to compare generated inputs and assertions with actual execution. JSON and
Markdown reports sit beside the HTML file. The viewer works offline.
The repository retains raw development generations and compact Markdown summaries;
replay recreates their derived JSON and HTML views when needed.

From this checkout:

```bash
python -m pip install -e ".[dev]"
testgen-bench validate
testgen-bench demo --report reports/testgen/demo.json
```

The demo uses reference assertions, never an LLM. Its 100% score checks the runner;
it is not model-performance evidence. Replay saved output without a model or API:

```bash
testgen-bench evaluate --input reports/testgen/heldout.jsonl --report reports/testgen/replay.json
```

The module form, `python -m raglab.testgen`, works too. Report paths must end in
`.json`; the command writes `.md` and `.html` alongside them.

## Generate an experiment

For hosted models, see the [API-key model guide](API_MODELS.md): OpenAI, Claude,
Gemini, Grok, DeepSeek, Groq, OpenRouter and custom compatible endpoints. Local
Ollama remains the default. `testgen-bench compare` replays multiple runs on the
same tasks into one comparison report.

Start Ollama and use an exact installed model name from `ollama list`. The
benchmark never downloads a model itself. Install the selected model explicitly
with `ollama pull qwen2.5-coder:3b` if needed. Use Ollama 0.34.0 for the recorded setup.
Older versions can ignore structured output constraints when Qwen thinking is
disabled; see the [upstream fix](https://github.com/ollama/ollama/pull/15901).

```bash
testgen-bench generate --model qwen2.5-coder:3b --split dev --output reports/testgen/my-dev.jsonl
testgen-bench evaluate --input reports/testgen/my-dev.jsonl --report reports/testgen/my-dev.json
```

Finish development decisions, then freeze the setup and run the entire final split:

```bash
testgen-bench freeze --model qwen2.5-coder:3b --output reports/testgen/my-plan.json
testgen-bench generate --model qwen2.5-coder:3b --split test --plan reports/testgen/my-plan.json --output reports/testgen/my-test.jsonl
testgen-bench evaluate --input reports/testgen/my-test.jsonl --report reports/testgen/my-test.json
```

The plan records task IDs, dataset/model/prompt/schema/scoring-code hashes, runtime
version, and inference settings. Generation rejects a changed plan or partial
held-out selection. Use new filenames: generation and freezing reject overwrites.
Interrupted attempts remain available; evaluation requires complete condition pairs.
To replay an earlier prompt protocol with fresh inference, pass the same
`--protocol` value to both `freeze` and `generate`.

After observing final results, do not tune against them and call another run
unseen evidence. The public synthetic split cannot establish absence of training
contamination or performance on real repositories.

## Protocol and scoring

Each condition uses an independent chat with the same model, settings, source,
schema, and four-test budget. `code_docs` appends the function contract. Neither
prompt contains mutants, reference assertions, or earlier responses.

Protocol v4 clarifies list/positional arguments with an unrelated format example.
Its schema enumerates JSON types and derives argument count from the signature.
It uses Ollama's [chat API](https://docs.ollama.com/api/chat) and
[structured outputs](https://docs.ollama.com/capabilities/structured-outputs).
The parser independently enforces shape, size, types, and finite-number bounds.

Settings: temperature 0, seed 42, 4096 context tokens, at most 1536 output tokens.
The Qwen 3.5 development alternative had thinking disabled and presence/repetition
penalties set to 0/1.0, recorded explicitly. The selected Qwen2.5-Coder model uses
the four common settings above. Fixed seeds are best-effort reproducibility.

A generated assertion is data: `{"args":[11,0,10],"expected":10}`.

1. Validate the entire generated suite.
2. Run every assertion against the correct implementation.
3. Any wrong assertion makes the suite a **false alarm**, earning zero bug credit.
4. Otherwise, run the same assertions against both mutants. A mismatched result or
   exception kills a mutant. Timeouts and worker failures never count as kills.

The primary score is **credited kills / all selected seeded mutants**. Failures
stay in the denominator. Reports separately count valid suites, false alarms,
format errors, provider failures, and execution errors. Valid suites can miss bugs.

Paired differences include a deterministic 2,000-resample task-bootstrap interval
(seed 1729). It estimates variation across these tasks, not across repeated model
generations. Intervals spanning zero do not support a general prompt advantage.
Code-only runs first; timings include warm-up/queue effects and are diagnostic.
Token counts are provider-reported; missing values remain unavailable.

## Evidence and checks

Records retain exact prompts, raw responses, hashes, model name/digest, options,
available timing/token metadata, and errors. Replay rejects mismatched provenance,
mixed configurations, duplicate records, and incomplete pairs. Hashes detect
accidental drift; they are not signatures proving origin. A model-tag change
invalidates an attempt while preserving its raw evidence.

Historical v1–v4 outputs remain replayable. Development diagnostics include the
[initial smoke run](../reports/testgen/smoke.md),
[repeat run](../reports/testgen/warm-smoke.md),
[v2 schema pilot](../reports/testgen/dev-v2-pilot.md), and
[v3 development run](../reports/testgen/dev-v3.md). The v2 pilot exposed our empty-
schema mistake: the local grammar backend constrained those values to objects.
Explicit JSON types fixed that defect; semantic assertion failures remained.

The [first Qwen v4 run](../reports/testgen/dev-v4-qwen.md) used Ollama 0.20.7.
A separate constant-schema probe returned Markdown fences, demonstrating that
format enforcement was inactive. That run is retained as an integration failure,
not evidence of Qwen's ability under the intended structured-output configuration.
The runtime was updated before freezing or generating any held-out outputs.

```bash
ruff check src tests conftest.py
pytest -q
testgen-bench validate
```

Set `RAGLAB_SKIP_DASHBOARD=1` to skip the existing RAG dashboard's pytest hook.
CI validates the dataset, produces a labeled reference-fixture report, and replays
the recorded held-out generations without an LLM.
Software-test results and model-performance measurements are separate.
The same workflow also enforces the RAG answer-quality thresholds and uploads both
sets of evidence, including when an evaluation fails.

## Execution boundary

Only trusted dataset Python executes. Model output is parsed JSON, never executable
Python. Each implementation gets a fresh `python -I -S` process, temporary working
directory, minimal environment, and a three-second timeout. Each assertion uses a
fresh function namespace.

This is process isolation, **not an arbitrary-code sandbox**. Use `--dataset` only
with reviewed code. Exact Python JSON representations are compared: booleans differ
from integers and there is no floating-point tolerance.

Reference suites pass their correct implementations and detect both mutants.
This validates the selected examples, not mathematical correctness or coverage of
all possible bugs. The project uses synthetic functions and local or API inference; it
contains no SAP source code or HANA integration.
