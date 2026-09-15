"""API contracts use local HTTP stubs; no credentials or paid model calls are needed."""
import json
import threading
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import pytest

from raglab import testgen, testgen_api
from raglab.testgen_compare import write_comparison
from raglab.testgen_view import render_html

KEY = "test-only-secret-12345"
RAW = json.dumps({"tests": [
    {"args": [5, 0, 10], "expected": 5}, {"args": [-1, 0, 10], "expected": 0},
    {"args": [11, 0, 10], "expected": 10}, {"args": [3, 3, 3], "expected": 3},
]})
RESPONSES = {
    "openai": {"model": "model-snapshot", "id": "resp_1", "status": "completed", "output": [
        {"type": "reasoning", "summary": [{"text": "private reasoning"}]},
        {"type": "message", "content": [{"type": "output_text", "text": RAW}]}],
        "usage": {"input_tokens": 20, "output_tokens": 15,
                  "input_tokens_details": {"cached_tokens": 5},
                  "output_tokens_details": {"reasoning_tokens": 10}}},
    "openai-chat": {"model": "model-snapshot", "id": "chat_1", "choices": [
        {"finish_reason": "stop", "message": {"content": RAW, "reasoning_content": "private reasoning"}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 15,
                  "prompt_tokens_details": {"cached_tokens": 5},
                  "completion_tokens_details": {"reasoning_tokens": 10}}},
    "anthropic": {"model": "model-snapshot", "id": "msg_1", "stop_reason": "end_turn", "content": [
        {"type": "thinking", "thinking": "private reasoning"}, {"type": "text", "text": RAW}],
        "usage": {"input_tokens": 10, "cache_read_input_tokens": 5,
                  "cache_creation_input_tokens": 5, "output_tokens": 15}},
    "gemini": {"modelVersion": "model-snapshot", "responseId": "gem_1", "candidates": [
        {"finishReason": "STOP", "content": {"parts": [
            {"thought": True, "text": "private reasoning"}, {"text": RAW}]}}],
        "usageMetadata": {"promptTokenCount": 20, "cachedContentTokenCount": 5,
                          "candidatesTokenCount": 5, "thoughtsTokenCount": 10}},
}


@pytest.fixture
def server():
    state = {"requests": [], "response": RESPONSES["openai"], "status": 200}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            state["requests"].append((self.path, dict(self.headers), json.loads(body)))
            self.send_response(state["status"])
            if state["status"] == 302:
                self.send_header("Location", "/leaked-key")
            self.end_headers()
            payload = state["response"]
            self.wfile.write(payload if isinstance(payload, bytes) else json.dumps(payload).encode())

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    state["url"] = f"http://127.0.0.1:{httpd.server_port}/v1"
    yield state
    httpd.shutdown()
    httpd.server_close()
    worker.join(timeout=2)


@pytest.fixture
def tasks():
    return testgen.load_tasks()


@pytest.mark.parametrize("provider,path,auth", [
    ("openai", "/v1/responses", "Authorization"),
    ("openai-chat", "/v1/chat/completions", "Authorization"),
    ("anthropic", "/v1/messages", "X-Api-Key"),
    ("gemini", "/v1/models/model-alias:generateContent", "X-Goog-Api-Key"),
])
def test_native_http_contract_and_offline_replay(provider, path, auth, server, tasks,
                                                 tmp_path, monkeypatch):
    server["response"] = RESPONSES[provider]
    config = testgen_api.configuration(provider, server["url"], "TEST_MODEL_KEY")
    monkeypatch.setenv("TEST_MODEL_KEY", KEY)
    output = tmp_path / "run.jsonl"
    testgen.generate(tasks, tasks[:1], output, "model-alias", None, api_config=config)
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(server["requests"]) == 2
    for index, (url, headers, body) in enumerate(server["requests"]):
        assert url == path
        assert headers[auth] == ("Bearer " + KEY if auth == "Authorization" else KEY)
        if provider == "anthropic":
            assert headers["Anthropic-Version"] == "2023-06-01"
        assert records[index]["request"]["body"] == body
        assert json.dumps(records[index]["prompt"]) in json.dumps(body)
        assert records[index]["raw"] == RAW
        assert records[index]["prompt_tokens"] == 20
        assert records[index]["completion_tokens"] == 15
        assert records[index]["model_digest"] is None
        assert records[index]["returned_model"] == "model-snapshot"
    assert KEY not in output.read_text()
    assert "private reasoning" not in output.read_text()
    with patch.object(testgen_api, "generate_one", side_effect=AssertionError("network during replay")):
        report = testgen.evaluate(tasks, records)
    assert all(row["status"] == "valid" for row in report["rows"])
    assert report["api_config"] == config
    html = render_html(report)
    assert "API: " + provider in html
    assert "Ollama " not in html
    assert "API response metadata" in html
    with pytest.raises(FileExistsError):
        testgen.generate(tasks, tasks[:1], output, "model-alias", None, api_config=config)
    assert len(server["requests"]) == 2


@pytest.mark.parametrize("provider", list(testgen_api.PROVIDERS))
def test_presets_and_missing_key_fail_without_request(provider, tasks, tmp_path, monkeypatch):
    config = testgen_api.configuration(provider, "https://example.invalid/v1", "ABSENT_MODEL_KEY")
    monkeypatch.delenv("ABSENT_MODEL_KEY", raising=False)
    with (patch.object(testgen_api, "generate_one") as call,
          pytest.raises(ValueError, match="Set ABSENT_MODEL_KEY locally")):
        testgen.generate(tasks, tasks[:1], tmp_path / "absent.jsonl", "id", None, api_config=config)
    call.assert_not_called()
    assert not (tmp_path / "absent.jsonl").exists()


@pytest.mark.parametrize("url", ["http://example.com/v1", "https://user:pass@example.com/v1",
                                     "https://example.com?key=secret", "https://example.com/#secret", ""])
def test_credential_url_and_insecure_remote_url_rejected(url):
    with pytest.raises(ValueError):
        testgen_api.configuration("compatible", url)


def test_provider_options_cannot_override_prompt_auth_or_sample_count():
    for options in ({"messages": []}, {"headers": {}}, {"api_key": KEY}, {"n": 2},
                    {"max_tokens": 3, "max_completion_tokens": 4}, {"max_tokens": 0}):
        with pytest.raises(ValueError):
            testgen_api.configuration("openai-chat", options=options)
    config = testgen_api.configuration("openai", options={"max_output_tokens": 8192,
                                                          "reasoning": {"effort": "low"}})
    body = testgen_api.request_for(config, "id", "prompt")["body"]
    assert "temperature" not in body and "seed" not in body
    assert body["store"] is False and body["max_output_tokens"] == 8192


@pytest.mark.parametrize("provider,status_field,status", [
    ("openai", "status", "incomplete"), ("openai-chat", "finish_reason", "length"),
    ("anthropic", "stop_reason", "max_tokens"), ("gemini", "finishReason", "MAX_TOKENS"),
    ("openai-chat", "finish_reason", None), ("gemini", "finishReason", "SAFETY"),
])
def test_truncation_and_unknown_completion_never_earn_credit(provider, status_field, status):
    response = deepcopy(RESPONSES[provider])
    target = response
    if provider == "openai-chat":
        target = response["choices"][0]
    elif provider == "gemini":
        target = response["candidates"][0]
    target[status_field] = status
    result = testgen_api.normalize(testgen_api.PROVIDERS[provider][0], response)
    assert result["generation_error"]
    assert result["raw"] == RAW


def test_refusals_tools_and_multiple_candidates_rejected():
    examples = []
    for field, value in (("refusal", "declined"), ("tool_calls", [{"function": {}}])):
        response = deepcopy(RESPONSES["openai-chat"])
        response["choices"][0]["message"][field] = value
        examples.append(("chat", response))
    response = deepcopy(RESPONSES["openai"])
    response["output"][1]["content"].append({"type": "refusal", "refusal": "declined"})
    examples.append(("responses", response))
    for provider, field in (("openai-chat", "choices"), ("gemini", "candidates")):
        response = deepcopy(RESPONSES[provider])
        response[field] *= 2
        examples.append((testgen_api.PROVIDERS[provider][0], response))
    for style, response in examples:
        assert testgen_api.normalize(style, response)["generation_error"]


def test_anthropic_refusal_details_and_reported_thinking_usage():
    response = deepcopy(RESPONSES["anthropic"])
    response["stop_details"] = {"type": "refusal", "explanation": "Declined"}
    response["usage"]["output_tokens_details"] = {"thinking_tokens": 8}
    result = testgen_api.normalize("messages", response)
    assert result["generation_error"] and result["raw"] == RAW
    assert result["reasoning_tokens"] == 8 and result["completion_tokens"] == 15


@pytest.mark.parametrize("provider", RESPONSES)
def test_missing_usage_is_unavailable_not_zero(provider):
    response = deepcopy(RESPONSES[provider])
    response.pop("usageMetadata" if provider == "gemini" else "usage")
    result = testgen_api.normalize(testgen_api.PROVIDERS[provider][0], response)
    assert result["prompt_tokens"] is None and result["completion_tokens"] is None
    assert result["prompt_cached_tokens"] is None and result["reasoning_tokens"] is None


def test_freeze_cli_needs_no_key_or_network(tmp_path):
    path = tmp_path / "plan.json"
    with (patch.object(testgen_api, "api_key", side_effect=AssertionError("key lookup")),
          patch.object(testgen, "api", side_effect=AssertionError("network"))):
        testgen.main(["freeze", "--provider", "openai", "--model", "id", "--output", str(path)])
    config = json.loads(path.read_text())["configuration"]
    assert len(config["task_ids"]) == 16 and config["adapter_sha256"]
    assert config["model_digest"] is None and config["api_config"]["provider"] == "openai"


@pytest.mark.parametrize("status,payload", [(302, b"redirect"), (401, KEY.encode()),
                                              (429, KEY.encode()), (200, b"malformed")])
def test_http_failures_no_redirects_no_retries_no_secret_echo(status, payload, server):
    server.update(status=status, response=payload)
    config = testgen_api.configuration("openai", server["url"])
    result = testgen_api.generate_one(config, testgen_api.request_for(config, "id", "prompt"), KEY)
    assert result["generation_error"]
    assert len(server["requests"]) == 1
    assert KEY not in json.dumps(result)


def test_key_echo_is_redacted_and_invalidated(server):
    response = deepcopy(RESPONSES["openai-chat"])
    response["choices"][0]["message"]["content"] = KEY
    server["response"] = response
    config = testgen_api.configuration("openai-chat", server["url"])
    result = testgen_api.generate_one(config, testgen_api.request_for(config, "id", "prompt"), KEY)
    assert result["raw"] == "[REDACTED]" and result["generation_error"]
    assert KEY not in json.dumps(result)


def saved_pair(tasks, config):
    records = []
    for condition in testgen.CONDITIONS:
        row = testgen.record_for(tasks[0], condition, testgen.digest(tasks), "id", None, "api")
        row.update(raw=RAW, api_config=config, options=config["options"],
                   request=testgen_api.request_for(config, "id", row["prompt"]))
        records.append(row)
    return records


def test_frozen_api_config_checked_before_network(tasks, tmp_path, monkeypatch):
    config = testgen_api.configuration("openai")
    selected = [task for task in tasks if task["split"] == "test"]
    plan = {"configuration": testgen.make_plan(tasks, "id", None, api_config=config)}
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    config_changed = testgen_api.configuration("openai", options={"max_output_tokens": 4096})
    with patch.object(testgen_api, "generate_one") as call:
        for selection, config_arg, plan_arg in ((selected, config, None),
                                                (selected[:1], config, plan),
                                                (selected, config_changed, plan)):
            with pytest.raises(ValueError):
                testgen.generate(tasks, selection, tmp_path / "bad.jsonl", "id", None,
                                 plan=plan_arg, api_config=config_arg)
    call.assert_not_called()
    assert not (tmp_path / "bad.jsonl").exists()


def test_api_shape_provenance_and_configuration_are_enforced(tasks):
    config = testgen_api.configuration("openai")
    rows = saved_pair(tasks, config)
    altered = deepcopy(rows)
    altered[0]["request"]["body"]["input"][0]["content"] = "changed"
    with pytest.raises(ValueError, match="provenance"):
        testgen.evaluate(tasks, altered)
    for cases in ([{"args": [1], "expected": 1}] * 4,
                  json.loads(RAW)["tests"][:3]):
        altered = deepcopy(rows)
        altered[0]["raw"] = json.dumps({"tests": cases})
        report = testgen.evaluate(tasks, altered)
        assert report["summary"]["code_only"]["invalid_generation"] == 1
        assert report["summary"]["code_only"]["mutation_score"] == 0
    altered = deepcopy(rows)
    altered[0]["generation_error"] = "truncated"
    report = testgen.evaluate(tasks, altered)
    assert report["summary"]["code_only"]["generation_error"] == 1
    assert report["summary"]["code_only"]["mutants_killed"] == 0


def test_rate_limit_skips_remaining_requests_and_keeps_denominator(tasks, tmp_path, monkeypatch):
    config = testgen_api.configuration("openai")
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    output = tmp_path / "limited.jsonl"
    with patch.object(testgen_api, "generate_one", return_value={
            "raw": "", "generation_error": "HTTP 429", "http_status": 429}) as call:
        testgen.generate(tasks, tasks[:2], output, "id", None, api_config=config)
    assert call.call_count == 1
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    report = testgen.evaluate(tasks, rows)
    assert len(rows) == 4 and rows[1]["request_sent"] is False
    assert rows[1]["latency_seconds"] is None
    assert all(item["generation_error"] == 2 and item["mutants_total"] == 4
               and item["mutation_score"] == 0 for item in report["summary"].values())


def test_changed_remote_identity_invalidates_whole_attempt(tasks, tmp_path, monkeypatch):
    config = testgen_api.configuration("openai")
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    output = tmp_path / "drift.jsonl"
    with (patch.object(testgen_api, "generate_one", side_effect=[
            {"raw": RAW, "returned_model": "before"}, {"raw": RAW, "returned_model": "after"}]),
          pytest.raises(ValueError, match="preserved and invalidated")):
        testgen.generate(tasks, tasks[:1], output, "id", None, api_config=config)
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert all(row["raw"] == RAW and row["generation_error"] for row in rows)
    assert testgen.evaluate(tasks, rows)["summary"]["code_docs"]["mutation_score"] == 0


def test_comparison_same_scope_required_and_json_only(tasks, tmp_path):
    report = testgen.evaluate(tasks, saved_pair(tasks, testgen_api.configuration("openai")))
    other = deepcopy(report)
    other["model"] = "<script>bad</script>"
    path = tmp_path / "compare.json"
    write_comparison([report, other], path)
    assert len(json.loads(path.read_text())["runs"]) == 2
    assert not path.with_suffix(".html").exists()
    assert not path.with_suffix(".md").exists()
    other["selected_tasks"] = ["different"]
    with pytest.raises(ValueError, match="identical"):
        write_comparison([report, other], path)
    other = deepcopy(report)
    other["source"] = "reference_fixture"
    with pytest.raises(ValueError, match="fixtures"):
        write_comparison([report, other], path)
