# Benchmarking models through Codex and Cursor

This extension uses the existing CLI logins to generate test data. It does not
extract login tokens or turn a subscription into a raw API key. Results measure
the selected model **through its CLI**, including that CLI's system instructions
and defaults. They cannot isolate the underlying model from the surrounding agent.

The [September 13 study](../reports/testgen/subscriptions-2026-09-13/README.md)
contains the catalog snapshot, account-availability classification, per-model
plans, raw generated test data and offline reports. `inventory.json` enumerates
six listed Codex models and 35 Cursor model families. It selects one standard-speed
setting per family, preferring medium or the unparameterized default; Grok 4.6
uses the user's Extra High preference. Auto, Fast duplicates and additional
reasoning variants are not separate model runs.

At the start of this study, Cursor's Other Models allowance was exhausted and
on-demand spending was disabled. Its Cursor Models allowance still permitted
Grok and Composer. All six Codex entries and three Cursor entries completed their
32-prompt runs: **nine models, 288 independent prompts**. The other 32 Cursor
entries were classified as blocked without making generation calls. A blocked
catalog entry has **no measured score**. The [final comparison](../reports/testgen/subscriptions-2026-09-13/comparison.html)
links each score to its original generated tests and execution evidence.

## Protocol

Each run uses the same 16 public test functions, two prompt conditions and strict
four-test validation as the recorded Qwen experiment. Every suite must pass the
correct function before receiving credit for detecting a seeded bug. All observed
generation failures remain in a started attempt's denominator.

Every task/condition launches a fresh CLI session in a new empty temporary
directory. The prompt contains only the function, the condition's documentation
and the existing generation instructions, preceded by a fixed instruction to
answer directly, use Ponytail's smallest correct test data and avoid all tools.
No reference assertions, mutants, prior responses or repository files are supplied.

Codex uses `exec --sandbox read-only --ephemeral --ignore-user-config
--skip-git-repo-check --json`, with medium reasoning, project-document loading
disabled and web search disabled. Existing authentication still works; no stored
credential file is read by the benchmark. Cursor uses `--mode ask --print
--output-format stream-json` and trusts only the fresh scratch directory.

The runner stops the CLI process and disqualifies a suite if its event stream
shows a tool call. This is an observed-tool-use check, not a claim of an operating
system sandbox for Cursor. Read-only Cursor mode and prompt instructions do not
remove every installed tool. Generated test data never becomes executable code.

Only visible final-answer text and public response metadata are retained. Reasoning
text and echoed environment messages are discarded. A nonzero exit, missing
completion event, timeout or tool attempt is a generation error. Each session has
a 240-second wall-clock limit. The benchmark never retries a completed/failed
generation; a CLI's internal connection handling remains part of that CLI.

Model IDs, CLI versions, prompt prefix, benchmark code and dataset are recorded in
the frozen plans. CLI model identity is not a verifiable weight digest. Cursor's
reported display name is retained when present; Codex exec does not always expose
an independently returned model name. Missing metadata remains unavailable.

Token counts include CLI instructions and other context. Codex input counts
already include cached input. Cursor's usage fields separate fresh input from
cache reads/writes, so the recorded input total adds those components. No prices
are inferred from tokens. Timings include CLI startup, network and queue overhead;
concurrent runs are not a controlled speed benchmark.

The public test split was already inspected during the original study. These are
extension results on that split, not new unseen evaluation evidence.

## Reproduce with existing logins

The matrix script is intended for this Windows CLI setup. Run from the repository
with its virtual environment active. Read-only inventory discovery makes no
generation calls:

```powershell
python scripts/run_subscription_benchmark.py --output-dir reports/testgen/my-subscriptions --cursor "$env:LOCALAPPDATA\cursor-agent\agent.ps1" --inventory-only
```

Check your current subscription allowances before generation. The catalog lists
models, not a guarantee of remaining quota. The script never enables on-demand
spending or changes subscription settings. Run selected exact catalog entries:

```powershell
python scripts/run_subscription_benchmark.py --output-dir reports/testgen/my-subscriptions --cursor "$env:LOCALAPPDATA\cursor-agent\agent.ps1" --provider codex --workers 2
python scripts/run_subscription_benchmark.py --output-dir reports/testgen/my-subscriptions --cursor "$env:LOCALAPPDATA\cursor-agent\agent.ps1" --provider cursor --models composer-2.5 cursor-grok-4.5-medium cursor-grok-4.6-xhigh --workers 2
```

Each model attempts 32 independent prompts. Quota, authentication, unavailable-model
and empty CLI failures stop further requests for that model; remaining slots are
marked skipped, rather than repeatedly probing the failure. Completed attempts
are replayed on a subsequent invocation. Partial attempts are preserved and
require inspection; they are not silently regenerated or filled with new samples.
Use a new directory for a deliberate new study.

To compare saved outputs, pass their JSONL files to the existing offline command:

```powershell
python -m raglab.testgen compare --input reports/testgen/heldout.jsonl reports/testgen/my-subscriptions/codex-gpt-6-astra.jsonl --report reports/testgen/my-subscriptions/comparison.json
```

CLI reports expose provider settings and per-suite metadata alongside the generated
assertions and actual execution outcomes. Both source types still enforce the
same data validation and mutation-credit rules.

Official transport references:
[Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode),
[Cursor CLI parameters](https://cursor.com/docs/cli/reference/parameters), and
[Cursor event output](https://cursor.com/docs/cli/reference/output-format).
