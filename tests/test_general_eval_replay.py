"""Keep archived reports replayable without authorizing new calls from old plans."""
import json
from unittest.mock import patch

import pytest

from raglab import general_eval, general_eval_judge, testgen_api, testgen_cli
from raglab.settings import PROJECT_ROOT


@pytest.fixture(params=[
    ("fixture", "fixture", general_eval),
    ("judge-fixture", "judge-fixture", general_eval_judge),
    ("smoke-2026-09-15", "codex", general_eval),
    ("smoke-2026-09-15", "cursor", general_eval),
    ("smoke-2026-09-15", "judge", general_eval_judge),
])
def archived_run(request):
    directory, stem, module = request.param
    directory = PROJECT_ROOT / "reports" / "general-eval" / directory
    plan = json.loads((directory / f"{stem}-plan.json").read_text(encoding="utf-8"))
    records = [json.loads(line) for line in
               (directory / f"{stem}-generations.jsonl").read_text(encoding="utf-8").splitlines()]
    report = json.loads((directory / f"{stem}-report.json").read_text(encoding="utf-8"))
    args = [general_eval.load_tasks()]
    if module is general_eval_judge:
        args.append(general_eval_judge.load_controls())
    return module, args, plan, records, report


def test_archived_reports_replay_exactly_offline(archived_run):
    module, args, plan, records, expected = archived_run
    before = general_eval.encoded([plan, records])
    with patch.object(testgen_api, "generate_one", side_effect=AssertionError("online replay")), \
            patch.object(testgen_cli, "generate_one", side_effect=AssertionError("online replay")):
        assert module.evaluate(*args, records, plan) == expected
    assert general_eval.encoded([plan, records]) == before


@pytest.mark.parametrize("field", ["scoring_sha256", "adapter_sha256", "policy"])
def test_archive_compatibility_rejects_unrecognized_plan_changes(archived_run, field):
    module, args, plan, records, _ = archived_run
    with pytest.raises(ValueError, match="Plan differs|not compatible"):
        module.evaluate(*args, records, {**plan, field: "unrecognized"})


def test_archive_compatibility_rejects_unverified_current_code(archived_run):
    module, args, plan, records, _ = archived_run
    make_plan = module.make_plan

    def changed_source(*args, **kwargs):
        return {**make_plan(*args, **kwargs), "scoring_sha256": "unverified-source"}

    with patch.object(module, "make_plan", side_effect=changed_source), \
            pytest.raises(ValueError, match="Plan differs|not compatible"):
        module.evaluate(*args, records, plan)


def test_archived_plans_cannot_authorize_new_generation(archived_run, tmp_path):
    module, args, plan, _, _ = archived_run
    output = tmp_path / "must-not-be-created.jsonl"
    with pytest.raises(ValueError, match="differs"):
        module.generate(*args, plan, output, plan["api_config"], plan["cli_config"])
    assert not output.exists()
