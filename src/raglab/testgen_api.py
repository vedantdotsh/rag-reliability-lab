"""Small stdlib adapters for text models. Credentials exist only in request headers."""
import json
import os
import re
from urllib import error, parse, request

# provider: (wire format, API root, environment variable)
PROVIDERS = {
    "openai": ("responses", "https://api.openai.com/v1", "OPENAI_API_KEY"),
    "openai-chat": ("chat", "https://api.openai.com/v1", "OPENAI_API_KEY"),
    "anthropic": ("messages", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
    "gemini": ("gemini", "https://generativelanguage.googleapis.com/v1beta", "GEMINI_API_KEY"),
    "xai": ("chat", "https://api.x.ai/v1", "XAI_API_KEY"),
    "deepseek": ("chat", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "groq": ("chat", "https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "openrouter": ("chat", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "compatible": ("chat", None, "MODEL_API_KEY"),
}
ALLOWED_OPTIONS = {
    "responses": {"temperature", "top_p", "reasoning", "text", "max_output_tokens"},
    "chat": {"temperature", "top_p", "seed", "reasoning_effort", "response_format",
             "max_tokens", "max_completion_tokens", "presence_penalty", "frequency_penalty"},
    "messages": {"temperature", "top_p", "top_k", "thinking", "output_config", "max_tokens"},
    "gemini": {"temperature", "topP", "topK", "seed", "thinkingConfig", "maxOutputTokens",
               "responseMimeType", "responseSchema", "responseJsonSchema"},
}
TOKEN_FIELD = {"responses": "max_output_tokens", "chat": "max_tokens",
               "messages": "max_tokens", "gemini": "maxOutputTokens"}
MAX_RESPONSE = 2 * 1024 * 1024


def configuration(provider, base_url=None, key_env=None, options=None):
    if provider not in PROVIDERS:
        raise ValueError("Unknown API provider")
    style, default_url, default_env = PROVIDERS[provider]
    base_url = (base_url or default_url or "").rstrip("/")
    url = parse.urlsplit(base_url)
    local = url.hostname in ("localhost", "127.0.0.1", "::1")
    if (not url.hostname or url.username or url.password or url.query or url.fragment
            or (url.scheme != "https" and not (local and url.scheme == "http"))):
        raise ValueError("API base URL must use HTTPS (HTTP only on loopback), with no credentials, "
                         "query or fragment; compatible requires --base-url")
    key_env = key_env or default_env
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_env):
        raise ValueError("--api-key-env must name an environment variable, not contain a key")
    options = {} if options is None else options
    if type(options) is not dict or set(options) - ALLOWED_OPTIONS[style]:
        raise ValueError("Unsupported API options; use only documented generation settings")
    # Copy via strict JSON so neither callers nor non-JSON values can mutate the plan.
    options = json.loads(json.dumps(options, allow_nan=False))
    token_field = "max_completion_tokens" if provider == "openai-chat" else TOKEN_FIELD[style]
    token_keys = set(options) & {"max_tokens", "max_completion_tokens", "max_output_tokens",
                                "maxOutputTokens"}
    if len(token_keys) > 1:
        raise ValueError("Supply only one output-token limit")
    token_field = next(iter(token_keys), token_field)
    options.setdefault(token_field, 1536)
    if type(options[token_field]) is not int or options[token_field] <= 0:
        raise ValueError("Output-token limit must be a positive integer")
    return {"provider": provider, "api_style": style, "base_url": base_url,
            "api_key_env": key_env, "options": options}


def api_key(config):
    key = os.environ.get(config["api_key_env"], "").strip()
    if not key or any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise ValueError(f"Set {config['api_key_env']} locally to a valid API key before generation")
    return key


def request_for(config, model, prompt):
    """Return the exact public URL and JSON body saved for offline provenance checks."""
    if not isinstance(model, str) or not model.strip():
        raise ValueError("A nonempty model ID is required")
    style, options = config["api_style"], config["options"]
    if style == "responses":
        path = "/responses"
        body = {"model": model, "input": [{"role": "user", "content": prompt}],
                "store": False, "stream": False, **options}
    elif style in ("chat", "messages"):
        path = "/chat/completions" if style == "chat" else "/messages"
        body = {"model": model, "messages": [{"role": "user", "content": prompt}],
                "stream": False, **options}
        if style == "chat":
            body["n"] = 1
    elif style == "gemini":
        path = "/models/" + parse.quote(model.removeprefix("models/"), safe="") + ":generateContent"
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"candidateCount": 1, **options}}
    else:
        raise ValueError("Unknown API wire format")
    return {"url": config["base_url"] + path, "body": body}


def normalize(style, response):
    """Keep visible output and usage, never reasoning blocks or provider error bodies."""
    result = {"raw": "", "returned_model": response.get("model"),
              "response_id": response.get("id"), "prompt_tokens": None,
              "prompt_cached_tokens": None, "completion_tokens": None, "reasoning_tokens": None}
    usage = response.get("usage") or {}
    bad = bool(response.get("error"))
    if style == "responses":
        messages = [item for item in response.get("output", []) if item.get("type") == "message"]
        blocks = [block for item in messages for block in item.get("content", [])]
        result["raw"] = "".join(b["text"] if b.get("type") == "output_text" else b["refusal"]
                                for b in blocks if b.get("type") in ("output_text", "refusal"))
        reason = response.get("status")
        bad |= (reason != "completed" or len(messages) != 1
                or any(i.get("status", "completed") != "completed" for i in messages)
                or any(b.get("type") != "output_text" for b in blocks)
                or any(i.get("type") not in ("message", "reasoning")
                       for i in response.get("output", [])))
        result.update(prompt_tokens=usage.get("input_tokens"),
                      completion_tokens=usage.get("output_tokens"),
                      prompt_cached_tokens=(usage.get("input_tokens_details") or {}).get(
                          "cached_tokens"),
                      reasoning_tokens=(usage.get("output_tokens_details") or {}).get(
                          "reasoning_tokens"))
    elif style == "chat":
        choices = response.get("choices", [])
        choice = choices[0] if len(choices) == 1 else {}
        message = choice.get("message") or {}
        result["raw"] = message.get("content") or message.get("refusal") or ""
        reason = choice.get("finish_reason")
        bad |= (reason != "stop" or bool(message.get("refusal"))
                or bool(message.get("tool_calls")) or bool(message.get("function_call")))
        result.update(prompt_tokens=usage.get("prompt_tokens"),
                      completion_tokens=usage.get("completion_tokens"),
                      prompt_cached_tokens=(usage.get("prompt_tokens_details") or {}).get(
                          "cached_tokens", usage.get("prompt_cache_hit_tokens")),
                      reasoning_tokens=(usage.get("completion_tokens_details") or {}).get(
                          "reasoning_tokens"))
    elif style == "messages":
        blocks = response.get("content", [])
        result["raw"] = "".join(b["text"] for b in blocks if b.get("type") == "text")
        reason = response.get("stop_reason")
        bad |= (reason != "end_turn" or bool(response.get("refusal"))
                or (response.get("stop_details") or {}).get("type") == "refusal"
                or any(b.get("type") not in ("text", "thinking", "redacted_thinking")
                       for b in blocks))
        counts = [usage.get("input_tokens"), usage.get("cache_read_input_tokens", 0),
                  usage.get("cache_creation_input_tokens", 0)]
        result.update(prompt_tokens=sum(counts) if all(type(n) is int for n in counts) else None,
                      completion_tokens=usage.get("output_tokens"),
                      prompt_cached_tokens=usage.get("cache_read_input_tokens"),
                      reasoning_tokens=(usage.get("output_tokens_details") or {}).get(
                          "thinking_tokens"))
    elif style == "gemini":
        choices = response.get("candidates", [])
        choice = choices[0] if len(choices) == 1 else {}
        blocks = (choice.get("content") or {}).get("parts", [])
        result["raw"] = "".join(b["text"] for b in blocks if "text" in b and not b.get("thought"))
        reason = choice.get("finishReason")
        bad |= (reason != "STOP" or bool((response.get("promptFeedback") or {}).get("blockReason"))
                or any("text" not in b for b in blocks))
        usage = response.get("usageMetadata") or {}
        visible, thoughts = usage.get("candidatesTokenCount"), usage.get("thoughtsTokenCount", 0)
        result.update(returned_model=response.get("modelVersion"),
                      response_id=response.get("responseId"),
                      prompt_tokens=usage.get("promptTokenCount"),
                      prompt_cached_tokens=usage.get("cachedContentTokenCount"),
                      completion_tokens=visible + thoughts if type(visible) is int
                      and type(thoughts) is int else None,
                      reasoning_tokens=usage.get("thoughtsTokenCount"))
    else:
        raise ValueError("Unknown API wire format")
    result["done_reason"] = reason
    for field in ("returned_model", "response_id", "done_reason"):
        if not isinstance(result[field], str):
            result[field] = None
    for field in ("prompt_tokens", "prompt_cached_tokens", "completion_tokens", "reasoning_tokens"):
        if type(result[field]) is not int or result[field] < 0:
            result[field] = None
    if not isinstance(result["raw"], str):
        result["raw"], bad = "", True
    if bad or not result["raw"].strip():
        result["generation_error"] = "API response was incomplete, refused, empty or unsupported"
    return result


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward a key to a redirect destination.
        return None


def generate_one(config, public_request, key):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if config["api_style"] == "messages":
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
    elif config["api_style"] == "gemini":
        headers["x-goog-api-key"] = key
    else:
        headers["Authorization"] = "Bearer " + key
    req = request.Request(public_request["url"], headers=headers,
                          data=json.dumps(public_request["body"], allow_nan=False).encode("utf-8"))
    try:
        with request.build_opener(NoRedirect()).open(req, timeout=240) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("Response exceeds limit")
        result = normalize(config["api_style"], json.loads(raw))
    except error.HTTPError as exc:
        # Server error text/headers may echo credentials. Keep the status only.
        result = {"raw": "", "generation_error": f"API HTTP {exc.code}; no retry was made",
                  "http_status": exc.code}
        exc.close()
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        result = {"raw": "", "generation_error": "API transport or malformed-response failure"}
    # Defense against a proxy echoing the actual key in visible output or identifiers.
    for field, value in list(result.items()):
        if isinstance(value, str) and key in value:
            result[field] = value.replace(key, "[REDACTED]")
            result["generation_error"] = "API echoed a credential; response redacted and rejected"
    return result
