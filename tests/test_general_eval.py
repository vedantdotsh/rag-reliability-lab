import json
from copy import deepcopy
from unittest.mock import patch

import pytest

from raglab import general_eval, general_eval_judge, testgen_api, testgen_cli


@pytest.fixture(scope="module")
def tasks():
    return general_eval.load_tasks()


def cli_plan(tasks, items=None, samples=3):
    config = testgen_cli.configuration("codex", "test-version")
    return general_eval.make_plan(tasks, "test-model", samples=samples,
                                  cli_config=config, item_ids=items)


def test_pack_is_audited_balanced_and_has_sparse_variants(tasks):
    audit = general_eval.validate_dataset(tasks)
    assert audit["base_problems"] == 60 and audit["prompt_variants"] == 100
    assert {domain: sum(task["domain"] == domain for task in tasks) for domain in {
        task["domain"] for task in tasks}} == {
            "instruction": 15, "reasoning": 15, "transformation": 15,
            "grounded_factuality": 15,
        }
    assert sum(len(task["variants"]) == 3 for task in tasks) == 20
    assert "abstain" not in tasks[48]["variants"]["base"].lower()
    assert "Use only the supplied evidence" in general_eval.prompt_for(tasks[45], "base")


def test_strict_scoring_handles_equivalence_constraints_and_hostile_json(tasks):
    object_task = next(task for task in tasks if task["id"] == "transform-09")
    assert general_eval.grade_response(
        object_task,
        '{"answer":{"c":7.0,"b":5.0,"a":1.0},"disposition":"answered"}',
    )["correct"]
    integer_task = next(task for task in tasks if task["id"] == "reason-01")
    assert not general_eval.grade_response(
        integer_task, '{"answer":4.0,"disposition":"answered"}')["correct"]
    for raw in (
        '{"answer":true,"disposition":"answered"}',
        '{"answer":null,"disposition":"answered"}',
        '{"answer":1e999,"disposition":"answered"}',
        '{"answer":4,"answer":5,"disposition":"answered"}',
        '{"answer":4,"disposition":"answered","extra":0}',
    ):
        result = general_eval.grade_response(integer_task, raw)
        assert not result["correct"]
    instruction = next(task for task in tasks if task["id"] == "inst-01")
    assert not general_eval.grade_response(
        instruction, '{"answer":"amber green cedar","disposition":"answered"}')["correct"]


def test_pass_metrics_distinguish_reliability_from_retry_opportunity():
    assert general_eval.pass_metrics(5, 4, 2) == (0.6, 1.0)
    assert general_eval.pass_metrics(3, 3, 3) == (1.0, 1.0)
    assert general_eval.pass_metrics(3, 0, 3) == (0.0, 0.0)
    with pytest.raises(ValueError):
        general_eval.pass_metrics(3, 4, 2)


def test_fixture_replay_is_complete_grouped_and_offline(tasks):
    plan = cli_plan(tasks)
    records = general_eval.fixture_records(tasks, plan)
    with patch.object(testgen_cli, "generate_one", side_effect=AssertionError("online during replay")):
        report = general_eval.evaluate(tasks, records, plan)
    assert len(records) == 300 and report["scope"] == {
        "base_problems": 60, "prompt_variants": 100, "samples": 3, "trials": 300,
    }
    assert report["summary"]["baseline_macro_success"] == 1
    assert report["summary"]["families"] == 45
    assert len(report["repeated_success"]) == 100
    assert all(row["pass_pow_n"] == 1 for row in report["repeated_success"])
    assert report["paired_robustness"]["summary"]["paired_base_items"] == 20
    assert "confidence interval" in report["paired_robustness"]["summary"][
        "uncertainty"]
    assert "task_bootstrap_95_ci" not in json.dumps(report)


def test_exact_logical_keys_and_plan_provenance_are_enforced(tasks):
    plan = cli_plan(tasks, ["inst-01"], samples=2)
    records = general_eval.fixture_records(tasks, plan)
    for altered, message in (
        (records[:-1], "incomplete"),
        (records + records[:1], "Duplicate"),
    ):
        with pytest.raises(ValueError, match=message):
            general_eval.evaluate(tasks, altered, plan)
    changed = deepcopy(records)
    changed[0]["prompt"] = "changed"
    with pytest.raises(ValueError, match="prompt provenance"):
        general_eval.evaluate(tasks, changed, plan)
    changed_plan = deepcopy(plan)
    changed_plan["samples"] = 9
    with pytest.raises(ValueError, match="Plan differs"):
        general_eval.evaluate(tasks, records, changed_plan)


def test_skipped_cells_suppress_reliability_and_robustness(tasks):
    plan = cli_plan(tasks, ["inst-01"], samples=2)
    records = general_eval.fixture_records(tasks, plan)
    records[0].update(raw="", generation_error="not sent", request_sent=False,
                      execution_status="skipped_after_block")
    report = general_eval.evaluate(tasks, records, plan)
    assert not report["summary"]["run_complete"]
    assert report["summary"]["all_variant_trial_success_rate"] is None
    assert report["summary"]["baseline_macro_success"] is None
    assert all(row["pass_pow_n"] is None and row["success_rate"] is None
               for row in report["repeated_success"])
    assert report["paired_robustness"]["summary"]["mean_variant_minus_base"] is None
    assert report["paired_robustness"]["summary"]["variant_wins"] is None
    assert all(item["delta"] is None for item in report["paired_robustness"]["items"])


def test_api_generation_records_exact_prompts_and_never_overwrites(tasks, tmp_path, monkeypatch):
    config = testgen_api.configuration("openai", key_env="GENERAL_TEST_KEY")
    monkeypatch.setenv("GENERAL_TEST_KEY", "secret-for-test")
    plan = general_eval.make_plan(tasks, "test-model", samples=1, api_config=config,
                                  item_ids=["reason-06"])
    output = tmp_path / "raw.jsonl"
    answer = json.dumps({"answer": 4, "disposition": "answered"})
    with patch.object(testgen_api, "generate_one", return_value={"raw": answer}) as call:
        general_eval.generate(tasks, plan, output, api_config=config)
        with pytest.raises(FileExistsError):
            general_eval.generate(tasks, plan, output, api_config=config)
    assert call.call_count == 1
    record = json.loads(output.read_text())
    assert record["request"]["body"]["input"][0]["content"] == record["prompt"]
    assert record["execution_status"] == "completed" and record["request_sent"] is True
    assert "secret-for-test" not in output.read_text()


def test_candidate_and_judge_stop_after_blocked_responses(tasks, tmp_path, monkeypatch):
    config = testgen_api.configuration("openai", key_env="GENERAL_TEST_KEY")
    monkeypatch.setenv("GENERAL_TEST_KEY", "secret-for-test")
    candidate_plan = general_eval.make_plan(
        tasks, "test-model", samples=2, api_config=config, item_ids=["reason-06"])
    controls = general_eval_judge.load_controls()
    judge_plan = general_eval_judge.make_plan(tasks, controls, "test-model", api_config=config)

    with patch.object(testgen_api, "generate_one", return_value={
            "raw": "", "generation_error": "rate limited", "http_status": 429,
            "blocked_reason": "policy"}) as call:
        candidate_output = tmp_path / "candidate-blocked.jsonl"
        general_eval.generate(tasks, candidate_plan, candidate_output, api_config=config)
        assert call.call_count == 1
    candidate = [json.loads(line) for line in candidate_output.read_text().splitlines()]
    assert candidate[0]["execution_status"] == "provider_error"
    assert candidate[1]["generation_error"] == "Skipped after policy; no retry was made"
    assert candidate[1]["request_sent"] is False and candidate[1]["latency_seconds"] is None

    with patch.object(testgen_api, "generate_one", return_value={
            "raw": "", "generation_error": "blocked", "blocked_reason": "policy"}) as call:
        judge_output = tmp_path / "judge-blocked.jsonl"
        general_eval_judge.generate(
            tasks, controls, judge_plan, judge_output, api_config=config)
        assert call.call_count == 1
    judge = [json.loads(line) for line in judge_output.read_text().splitlines()]
    assert judge[0]["execution_status"] == "provider_error"
    assert judge[1]["generation_error"] == (
        "Skipped after blocking transport response; no retry was made")
    assert judge[1]["request_sent"] is False and judge[1]["latency_seconds"] is None


def test_candidate_and_judge_stop_after_harness_errors(tasks, tmp_path, monkeypatch):
    config = testgen_api.configuration("openai", key_env="GENERAL_TEST_KEY")
    monkeypatch.setenv("GENERAL_TEST_KEY", "secret-for-test")
    controls = general_eval_judge.load_controls()
    runs = [
        (general_eval.make_plan(
            tasks, "test-model", samples=2, api_config=config, item_ids=["reason-06"]),
         lambda plan, output: general_eval.generate(
             tasks, plan, output, api_config=config)),
        (general_eval_judge.make_plan(tasks, controls, "test-model", api_config=config),
         lambda plan, output: general_eval_judge.generate(
             tasks, controls, plan, output, api_config=config)),
    ]
    for index, (plan, run) in enumerate(runs):
        output = tmp_path / f"harness-{index}.jsonl"
        with patch.object(testgen_api, "generate_one", side_effect=OSError("offline")) as call:
            run(plan, output)
            assert call.call_count == 1
        records = [json.loads(line) for line in output.read_text().splitlines()]
        assert records[0]["execution_status"] == "harness_error"
        assert records[0]["generation_error"] == "offline"
        assert records[0]["request_sent"] is False
        assert records[1]["execution_status"] == "skipped_after_block"
        assert records[1]["generation_error"] == (
            "Skipped after transport failure; no retry was made")
        assert all(record["latency_seconds"] is None for record in records)


def test_missing_execution_status_is_candidate_only_compatibility(tasks):
    candidate_plan = cli_plan(tasks, ["reason-06"], samples=1)
    candidate = general_eval.fixture_records(tasks, candidate_plan)
    candidate[0].pop("execution_status")
    assert general_eval.evaluate(tasks, candidate, candidate_plan)["summary"]["run_complete"]

    controls = general_eval_judge.load_controls()
    config = testgen_api.configuration("openai")
    judge_plan = general_eval_judge.make_plan(tasks, controls, "judge-fixture", api_config=config)
    judge = general_eval_judge.fixture_records(tasks, controls, judge_plan)
    judge[0].pop("execution_status")
    with pytest.raises(ValueError, match="Unknown execution status"):
        general_eval_judge.evaluate(tasks, controls, judge, judge_plan)


def test_cli_uses_neutral_prefix_and_preserves_no_tools_seam(tasks, tmp_path):
    config = testgen_cli.configuration("codex", "test-version")
    plan = general_eval.make_plan(tasks, "test-model", samples=1, cli_config=config,
                                  item_ids=["reason-06"])
    output = tmp_path / "raw.jsonl"
    answer = json.dumps({"answer": 4, "disposition": "answered"})
    with patch.object(testgen_cli, "generate_one", return_value={"raw": answer}) as call:
        general_eval.generate(tasks, plan, output, cli_config=config, cli_executable="codex")
    assert call.call_args.args[-1] == general_eval.CLI_PREFIX
    record = json.loads(output.read_text())
    assert record["cli_prompt"].startswith(general_eval.CLI_PREFIX)
    assert general_eval.CLI_PREFIX != testgen_cli.PREFIX


def test_model_identity_drift_is_rejected_without_rewriting_raw(tasks, tmp_path, monkeypatch):
    config = testgen_api.configuration("openai", key_env="GENERAL_TEST_KEY")
    monkeypatch.setenv("GENERAL_TEST_KEY", "secret-for-test")
    plan = general_eval.make_plan(tasks, "test-model", samples=2, api_config=config,
                                  item_ids=["reason-06"])
    output = tmp_path / "drift.jsonl"
    answer = json.dumps({"answer": 47, "disposition": "answered"})
    with patch.object(testgen_api, "generate_one", side_effect=[
            {"raw": answer, "returned_model": "before"},
            {"raw": answer, "returned_model": "after"},
    ]):
        general_eval.generate(tasks, plan, output, api_config=config)
    before = output.read_bytes()
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert all(record["raw"] == answer for record in records)
    with pytest.raises(ValueError, match="identity changed"):
        general_eval.evaluate(tasks, records, plan)
    assert output.read_bytes() == before


def test_fixture_report_escapes_evidence_and_is_prominently_labeled(tasks):
    plan = cli_plan(tasks, ["inst-01"], samples=1)
    records = general_eval.fixture_records(tasks, plan)
    records[0]["raw"] = '<script>alert("x")</script>'
    page = general_eval.render_html(general_eval.evaluate(tasks, records, plan))
    assert "Reference fixture: no model calls were made" in page
    assert "<script>" not in page and "&lt;script&gt;" in page


def test_judge_controls_validate_and_both_orders_replay(tasks, tmp_path):
    controls = general_eval_judge.load_controls()
    audit = general_eval_judge.validate_controls(tasks, controls)
    assert audit["controls"] == 12 and {"wrong_entity", "equivalent"} <= set(audit["kinds"])
    config = testgen_api.configuration("openai")
    plan = general_eval_judge.make_plan(tasks, controls, "judge-fixture", api_config=config)
    records = general_eval_judge.fixture_records(tasks, controls, plan)
    report = general_eval_judge.evaluate(tasks, controls, records, plan)
    assert len(records) == 24 and report["scheduled_success_rate"] == 1
    assert report["valid_presentation_accuracy"] == 1
    assert report["judge_errors"] == 0 and report["order_flips"] == 0
    assert {row["order"] for row in report["rows"]} == {"ab", "ba"}
    records[0]["raw"] = '<script>alert("x")</script>'
    report = general_eval_judge.evaluate(tasks, controls, records, plan)
    assert report["judge_errors"] == 1
    assert report["scheduled_success_rate"] == round(23 / 24, 4)
    assert report["valid_presentation_accuracy"] == 1
    assert report["false_accept_denominator"] + report["false_reject_denominator"] == 23
    path = tmp_path / "judge.json"
    general_eval_judge.write_report(report, path)
    assert json.loads(path.read_text())["judge_errors"] == 1
    assert not path.with_suffix(".html").exists()


def test_terminal_demos_need_no_output_files(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    general_eval.main(["demo"])
    output = capsys.readouterr().out
    assert "General LLM evaluation" in output
    assert "Reference fixture: no model calls were made" in output
    assert "Status: complete" in output and "Failed items: none" in output
    general_eval_judge.main(["demo"])
    output = capsys.readouterr().out
    assert "General judge controls" in output
    assert "false accepts 0/" in output and "false rejects 0/" in output
    assert not list(tmp_path.iterdir())


def test_freeze_commands_never_overwrite_manifests(tmp_path):
    general_path = tmp_path / "general-plan.json"
    general_args = ["freeze", "--transport", "cli", "--provider", "codex",
                    "--model", "test-model", "--cli-version", "test", "--items", "reason-06",
                    "--output", str(general_path)]
    general_eval.main(general_args)
    with pytest.raises(FileExistsError):
        general_eval.main(general_args)
    judge_path = tmp_path / "judge-plan.json"
    judge_args = ["freeze", "--transport", "cli", "--provider", "codex",
                  "--model", "test-model", "--cli-version", "test",
                  "--output", str(judge_path)]
    general_eval_judge.main(judge_args)
    with pytest.raises(FileExistsError):
        general_eval_judge.main(judge_args)
