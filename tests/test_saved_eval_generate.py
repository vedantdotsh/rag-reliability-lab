import json
from unittest.mock import patch

import pytest

from raglab import saved_eval_generate, testgen_api, testgen_cli
from raglab.saved_eval import evaluate, load_records


def _records():
    return [
        {"id": "one", "input": "Say alpha", "response": "", "expected": "alpha",
         "scorer": "exact", "category": "text"},
        {"id": "two", "input": "Say nothing", "response": "", "expected": "",
         "scorer": "exact", "category": "text"},
    ]


def test_api_generation_sends_only_inputs_and_keeps_failures(tmp_path):
    output = tmp_path / "generated.jsonl"
    config = testgen_api.configuration("compatible", "http://127.0.0.1:8765")
    with patch.object(testgen_api, "api_key", return_value="secret"), patch.object(
        testgen_api, "generate_one", side_effect=[
            {"raw": "alpha", "returned_model": "actual"},
            {"raw": "", "generation_error": "provider stopped"},
        ]
    ) as call:
        failures = saved_eval_generate.generate(
            _records(), output, "requested", api_config=config
        )

    assert failures == 1
    assert [args.args[1]["body"]["messages"][0]["content"] for args in call.call_args_list] == [
        "Say alpha", "Say nothing"
    ]
    assert all("expected" not in json.dumps(args.args[1]) for args in call.call_args_list)
    records = load_records(output)
    report = evaluate(records, output)
    assert report["summary"] == {"total": 2, "passed": 1, "failed": 1}
    assert report["cases"][1]["reason"] == "generation failed: provider stopped"
    assert records[0]["generation"]["returned_model"] == "actual"


def test_cli_generation_uses_independent_adapter_calls(tmp_path):
    output = tmp_path / "generated.jsonl"
    config = testgen_cli.configuration("codex", "test")
    with patch.object(testgen_cli, "generate_one", return_value={"raw": "answer"}) as call:
        assert saved_eval_generate.generate(
            _records(), output, "model", cli_config=config, cli_executable=__file__
        ) == 0

    assert call.call_count == 2
    assert [args.args[3] for args in call.call_args_list] == ["Say alpha", "Say nothing"]
    assert all("expected" not in args.args[4] for args in call.call_args_list)


def test_partial_generated_run_is_refused(tmp_path):
    output = tmp_path / "generated.jsonl"
    config = testgen_cli.configuration("codex", "test")
    with patch.object(testgen_cli, "generate_one", return_value={"raw": "answer"}):
        saved_eval_generate.generate(
            _records(), output, "model", cli_config=config, cli_executable=__file__
        )
    output.write_text(output.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="partial or out of order"):
        load_records(output)


def test_existing_output_is_preserved(tmp_path):
    output = tmp_path / "exists.jsonl"
    output.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        saved_eval_generate.generate(
            _records(), output, "model", cli_config=testgen_cli.configuration("codex", "test"),
            cli_executable=__file__,
        )
    assert output.read_text(encoding="utf-8") == "keep"


def test_cli_preflight_rejects_missing_executable_before_creating_output(tmp_path):
    output = tmp_path / "generated.jsonl"
    with pytest.raises(ValueError, match="--cli-executable"):
        saved_eval_generate.generate(
            _records(), output, "model", cli_config=testgen_cli.configuration("codex", "test")
        )
    assert not output.exists()
