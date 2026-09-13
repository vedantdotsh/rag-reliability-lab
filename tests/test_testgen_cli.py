import json

import pytest

from raglab import testgen_cli

RAW = json.dumps({"tests": []})


def codex_events(usage=None, *extra):
    events = [{"type": "item.completed", "item": {"type": "agent_message", "text": RAW}}]
    if usage is not None:
        events.append({"type": "turn.completed", "usage": usage})
    events.extend(extra)
    return events


def cursor_events(*extra):
    events = [{"type": "system", "subtype": "init", "model": "Display Name"}]
    events.extend(extra)
    return events


def test_codex_success_extracts_visible_text_and_counts():
    usage = {
        "input_tokens": 20,
        "cached_input_tokens": 5,
        "output_tokens": 10,
        "reasoning_output_tokens": 4,
    }
    result = testgen_cli.normalize_cli("codex", codex_events(usage=usage))
    assert result["raw"] == RAW
    assert result["prompt_tokens"] == 20
    assert result["prompt_cached_tokens"] == 5
    assert result["completion_tokens"] == 10
    assert result["reasoning_tokens"] == 4
    assert result["done_reason"] == "turn.completed"
    assert result.get("generation_error") is None


@pytest.mark.parametrize("item_type", ["command_execution", "file_change", "mcp_tool_call", "web_search"])
def test_codex_disqualifies_tool_or_unsupported_item(item_type):
    result = testgen_cli.normalize_cli("codex", codex_events(
        None,
        {"type": "item.started", "item": {"type": item_type, "text": "ignore"}},
    ))
    assert result["generation_error"]
    assert result["raw"] == RAW


def test_codex_turn_failed_keeps_visible_text_and_marks_failed():
    result = testgen_cli.normalize_cli("codex", [
        {"type": "item.completed", "item": {"type": "agent_message", "text": RAW}},
        {"type": "turn.failed", "error": {"message": "failed"}},
    ])
    assert result["raw"] == RAW
    assert result["generation_error"]


def test_codex_without_turn_completed_is_disqualified():
    result = testgen_cli.normalize_cli("codex", [{"type": "item.completed", "item": {"type": "agent_message", "text": RAW}}])
    assert result["raw"] == RAW
    assert result["generation_error"]


def test_cursor_success_extracts_visible_result_and_aggregates_tokens():
    usage = {
        "inputTokens": 10,
        "outputTokens": 6,
        "cacheReadTokens": 2,
        "cacheWriteTokens": 3,
    }
    result = testgen_cli.normalize_cli("cursor", cursor_events({
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": RAW,
        "usage": usage,
    }))
    assert result["raw"] == RAW
    assert result["returned_model"] == "Display Name"
    assert result["prompt_tokens"] == 15
    assert result["prompt_cached_tokens"] == 2
    assert result["completion_tokens"] == 6
    assert result["done_reason"] == "success"
    assert result.get("generation_error") is None


def test_cursor_thinking_event_is_ignored_and_tool_call_disqualifies():
    result = testgen_cli.normalize_cli("cursor", cursor_events(
        {"type": "result", "subtype": "success", "is_error": False, "result": RAW},
        {"type": "thinking", "text": "private reason"},
    ))
    assert result["raw"] == RAW
    assert result.get("generation_error") is None

    blocked = testgen_cli.normalize_cli("cursor", cursor_events(
        {"type": "result", "subtype": "success", "is_error": False, "result": RAW},
        {"type": "tool_call"},
    ))
    assert blocked["raw"] == RAW
    assert blocked["generation_error"]


def test_cursor_failed_event_and_returncode_error_are_disqualified():
    failed = testgen_cli.normalize_cli("cursor", cursor_events({
        "type": "result",
        "subtype": "error",
        "is_error": True,
        "result": RAW,
    }))
    assert failed["raw"] == RAW
    assert failed["generation_error"]

    nonzero = testgen_cli.normalize_cli(
        "cursor",
        cursor_events({"type": "result", "subtype": "success", "is_error": False, "result": RAW}),
        returncode=1,
    )
    assert nonzero["generation_error"]
    assert nonzero["raw"] == RAW


def test_cursor_missing_result_is_disqualified_and_unchanged_prompt_is_empty():
    result = testgen_cli.normalize_cli("cursor", cursor_events())
    assert result["raw"] == ""
    assert result["generation_error"]


def test_cli_provenance_and_four_case_rule():
    from raglab import testgen

    tasks = testgen.load_tasks()
    config = testgen_cli.configuration("codex", "test-version")
    rows = []
    for condition in testgen.CONDITIONS:
        row = testgen.record_for(tasks[0], condition, testgen.digest(tasks), "test-model", None, "cli")
        row.update(raw=RAW, cli_config=config, options=config,
                   cli_prompt=testgen_cli.cli_prompt(row["prompt"]))
        rows.append(row)
    report = testgen.evaluate(tasks, rows)
    assert report["cli_config"] == config
    assert all(s["invalid_generation"] == 1 for s in report["summary"].values())
    rows[0]["cli_prompt"] = "changed"
    with pytest.raises(ValueError, match="provenance"):
        testgen.evaluate(tasks, rows)
