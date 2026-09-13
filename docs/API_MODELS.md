# Run the benchmark with API-key models

The same paired prompts, four-test budget and strict scoring work with hosted text
models. Pick an exact model ID available to your API account. No model is downloaded
or selected automatically, and the runner never silently switches models.

| `--provider` | API format | Default key environment variable |
|---|---|---|
| `ollama` | Local Ollama chat | None |
| `openai` | OpenAI Responses | `OPENAI_API_KEY` |
| `openai-chat` | OpenAI Chat Completions | `OPENAI_API_KEY` |
| `anthropic` | Claude Messages | `ANTHROPIC_API_KEY` |
| `gemini` | Gemini generateContent | `GEMINI_API_KEY` |
| `xai` | Grok chat completions | `XAI_API_KEY` |
| `deepseek` | DeepSeek chat completions | `DEEPSEEK_API_KEY` |
| `groq` | Groq chat completions | `GROQ_API_KEY` |
| `openrouter` | OpenRouter chat completions | `OPENROUTER_API_KEY` |
| `compatible` | Custom OpenAI-compatible chat endpoint | `MODEL_API_KEY` |

Run `python -m raglab.testgen providers` to see the configured API roots. Override
the root with `--base-url` and the environment variable **name** with `--api-key-env`.
Use an API root such as `https://your-provider.example/v1`, without `/chat/completions`.
The `compatible` provider requires an explicit root.

This covers these text-generation formats, not literally every model or service.
Image/audio-only models, OAuth-only services, AWS-signed Bedrock requests and
Azure's distinct deployment/authentication routes need separate adapters. A
compatible service must accept bearer authentication and return a single text
choice with `finish_reason: "stop"`. Model access and supported options vary.

## First run on Windows

Use the project's virtual environment, then enter a provider key at a hidden local
prompt. This PowerShell sequence keeps the key out of command history and removes
it from the shell environment after generation. Never paste keys into chat or
put them in an options file. The application does not automatically load `.env`.

```powershell
. .venv\Scripts\Activate.ps1
$modelId = Read-Host 'Exact OpenAI model ID available to your API account'
$keyInput = Read-Host 'OpenAI API key (hidden)' -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $keyInput).Password
try {
    python -m raglab.testgen generate --provider openai --model $modelId --split dev --limit 1 --output reports/testgen/openai-pilot.jsonl
} finally {
    Remove-Item Env:\OPENAI_API_KEY
    $keyInput.Dispose()
}
python -m raglab.testgen evaluate --input reports/testgen/openai-pilot.jsonl --report reports/testgen/openai-pilot.json
Start-Process reports/testgen/openai-pilot.html
```

The pilot sends **two requests**: one per prompt condition. A full dev run sends
16 requests; a full test run sends 32. Generation invokes your chosen API and may
incur charges. Freezing, replaying and comparing make no model calls and need no key.
Use a different provider flag and its corresponding key variable for other services.

The HTML files are static reports. Configure keys in the shell running generation;
the browser neither receives keys nor makes inference requests. API reports show
the provider and recorded settings. Each evidence row includes response metadata.

## Model-specific settings

Hosted defaults set an output limit of 1,536 tokens and leave temperature, seed
and reasoning effort to the provider. Some reasoning models need a larger budget.
Decide on settings during development, before freezing the test run. The runner
does not retry requests with different options when a model rejects a parameter.

Save provider-native settings in a JSON file and pass it with `--api-options` to
both `freeze` and `generate`. For example, an OpenAI Responses options file:

```json
{"max_output_tokens": 8192, "reasoning": {"effort": "low"}}
```

Only use reasoning settings supported by your chosen model. Token-limit fields:

| API format | Default field | Other supported settings |
|---|---|---|
| OpenAI Responses | `max_output_tokens` | `temperature`, `top_p`, `reasoning`, `text` |
| OpenAI Chat | `max_completion_tokens` | `temperature`, `top_p`, `seed`, `reasoning_effort`, `response_format`, presence/frequency penalties |
| Other compatible chat | `max_tokens` | Same chat fields; `max_completion_tokens` can replace `max_tokens` |
| Claude Messages | `max_tokens` | `temperature`, `top_p`, `top_k`, `thinking`, `output_config` |
| Gemini | `maxOutputTokens` | `temperature`, `topP`, `topK`, `seed`, `thinkingConfig`, `responseMimeType`, `responseSchema`, `responseJsonSchema` |

Gemini options go directly inside `generationConfig`; do not wrap them in another
object. Only one token-limit field is permitted. Fields for keys, headers, tools,
messages, model selection and additional candidates cannot override the benchmark.
Provider validation still determines which generation settings a model accepts.

The prompt requests JSON and the local evaluator enforces the same schema for
every model. Hosted defaults **do not request native constrained decoding**. To use
it, select the provider's supported format option explicitly and record it in your
options file. For example, chat JSON mode is
`{"response_format":{"type":"json_object"}}`; Gemini JSON mode is
`{"responseMimeType":"application/json"}`. Neither mode guarantees correct assertions.
The historical Ollama run used native schema constraints; account for that difference
when interpreting comparisons with hosted runs.

## Freeze, run and compare

After the pilot, configure the key locally again. Use identical provider, model,
root and options for freezing and generation. These commands assume an environment
key is already set and use the `$modelId` you selected:

```powershell
python -m raglab.testgen freeze --provider openai --model $modelId --output reports/testgen/openai-plan.json
python -m raglab.testgen generate --provider openai --model $modelId --split test --plan reports/testgen/openai-plan.json --output reports/testgen/openai-test.jsonl
python -m raglab.testgen evaluate --input reports/testgen/openai-test.jsonl --report reports/testgen/openai-test.json
python -m raglab.testgen compare --input reports/testgen/heldout.jsonl reports/testgen/openai-test.jsonl --report reports/testgen/models.json
Start-Process reports/testgen/models.html
```

Add more generation files after `--input` to extend the table. Comparison replays
each run offline and rejects different datasets, protocols, task selections or
splits. Reference fixtures cannot enter model comparisons. JSON retains each
replayed run's full evidence; Markdown and HTML provide a side-by-side table.
There is no guessed dollar cost or general capability ranking.

Use new filenames for each attempt. Generation and freezing refuse to overwrite
existing evidence. A completed plan freezes request settings, prompts, task IDs,
schema and code hashes. Remote model weights cannot be hashed or verified. Prefer
dated/snapshot IDs when offered; aliases may change even if their name stays the
same. Differing returned model names invalidate the whole attempt while preserving
the outputs. Missing returned names remain unavailable.

The original Qwen test split has already been observed. New runs are an extension
on that public split, not fresh unseen evidence. Original generation code and its
plan are preserved at commit `4de95f0`; use that commit to reproduce the original
frozen setup. Current code still replays those historical outputs unchanged.

## Failures, tokens and credentials

One request is attempted per task/condition, with no automatic retries, fallback
models or capability probes. Truncation, refusal, unknown completion status,
tool output, empty output and malformed responses earn zero credit. Available
visible text is retained for diagnosis; reasoning/thinking text is excluded.
HTTP 401, 403 or 429 stops further API requests in that attempt. Remaining slots
are recorded as skipped generation failures, keeping the full score denominator.

Input/output totals are provider-reported, not estimated. Missing values stay
unavailable. Output totals include reported reasoning: OpenAI already includes it;
Gemini candidate and thought counts are added. Claude input totals add uncached,
cache-read and cache-creation tokens; its output total may include thinking without
a separate reasoning count. Cache counts are also recorded where available.
Tokenizers and budget semantics differ, so equal token limits do not imply equal
compute. Latency includes network and queue overhead; skipped requests have no time.

Keys are read from environment variables only and sent in authentication headers.
They are excluded from the saved request body, URL and results. API roots require
HTTPS except on loopback; redirects are refused. Error bodies are not logged, and
an echoed key is redacted and makes the response invalid. Generated Python workers
receive the existing minimal environment, excluding provider keys. Only reviewed
dataset functions execute; model output remains JSON data.

The tests exercise all four wire formats through a local HTTP server, including
authentication headers, response parsing, refusals, truncation, redirects, key
redaction, frozen settings and offline replay. These are adapter tests, not evidence
of live account/model availability or measured hosted-model performance.

Official API references checked for this implementation:
[OpenAI Responses](https://developers.openai.com/api/reference/cli/resources/responses/methods/create),
[OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
[Claude Messages](https://platform.claude.com/docs/en/api/messages/create),
[Gemini generateContent](https://ai.google.dev/api/generate-content),
[xAI](https://docs.x.ai/developers/rest-api-reference/inference/chat),
[DeepSeek](https://api-docs.deepseek.com/),
[Groq](https://console.groq.com/docs/openai), and
[OpenRouter](https://openrouter.ai/docs/quickstart).
