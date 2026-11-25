import json
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from raglab.data import load_cases, load_documents
from raglab.evaluation import (
    check_gate,
    compare_reports,
    evaluate,
    write_json_report,
    write_markdown_report,
)
from raglab.models import Document, EvalCase

DOCUMENTS = [Document("limits", "API limits", "The API allows 600 requests per minute.")]
CASES = [EvalCase("limit", "How many API requests per minute?", ("limits",),
                  ("600 requests per minute",))]


class EvaluationTests(unittest.TestCase):
    def test_end_to_end_evaluation(self):
        documents = [Document("limits", "API limits", "The API allows 600 requests per minute.")]
        cases = [
            EvalCase(
                "limit",
                "How many API requests are allowed per minute?",
                ("limits",),
                ("600 requests per minute",),
            )
        ]
        report = evaluate(documents, cases)
        self.assertEqual(report.metrics["hit_rate_at_3"], 1.0)
        self.assertEqual(report.metrics["required_phrase_coverage"], 1.0)
        self.assertEqual(report.metrics["faithfulness"], 1.0)

    def test_api_model_uses_same_retrieval_scoring_and_comparison(self):
        from raglab import testgen_api
        from raglab.answering import ABSTENTION_ANSWER

        documents = DOCUMENTS + [Document("hidden", "Other", "LABEL_ONLY_SECRET")]
        cases = CASES + [EvalCase("unknown", "Who won chess?", (), (), should_abstain=True)]
        baseline = evaluate(documents, cases)
        config = testgen_api.configuration("compatible", "http://127.0.0.1:8765")
        with patch.object(testgen_api, "api_key", return_value="test-key"), patch.object(
            testgen_api, "generate_one", side_effect=[
                {"raw": baseline.cases[0].answer}, {"raw": ABSTENTION_ANSWER},
            ]
        ) as call, patch("raglab.evaluation.time.perf_counter", side_effect=[0, 1, 2, 4]):
            candidate = evaluate(documents, cases, model="chosen-model", api_config=config)
        self.assertEqual(candidate.benchmark_sha256, baseline.benchmark_sha256)
        self.assertEqual(candidate.config["generator"], "llm")
        self.assertEqual(candidate.config["model"], "chosen-model")
        self.assertEqual(candidate.config["api"], config)
        self.assertNotIn("test-key", str(candidate.to_dict()))
        self.assertEqual(candidate.metrics["p95_latency_ms"], 2000)
        self.assertFalse(check_gate(candidate.metrics, {"p95_latency_ms_max": 50})["passed"])
        self.assertTrue(compare_reports(baseline.to_dict(), candidate.to_dict())["passed"])
        for index, invocation in enumerate(call.call_args_list):
            request = invocation.args[1]
            self.assertEqual(request["body"]["model"], "chosen-model")
            prompt = request["body"]["messages"][0]["content"]
            self.assertIn(cases[index].question, prompt)
            self.assertNotIn("LABEL_ONLY_SECRET", prompt)
            self.assertNotIn("required_facts", prompt)
            self.assertNotIn("expected_doc_ids", prompt)
            if index == 0:
                self.assertIn("[limits]", prompt)
                self.assertIn(DOCUMENTS[0].text, prompt)
            else:
                self.assertNotIn(DOCUMENTS[0].text, prompt)

    def test_api_errors_never_become_successful_answers(self):
        from raglab import testgen_api

        config = testgen_api.configuration("compatible", "http://127.0.0.1:8765")
        for result in ({"raw": "valid-looking answer", "generation_error": "truncated"},
                       {"raw": ""}, {"raw": None}):
            with self.subTest(result=result), patch.object(
                testgen_api, "api_key", return_value="test-key"
            ), patch.object(testgen_api, "generate_one", return_value=result), self.assertRaises(
                ValueError
            ):
                evaluate(DOCUMENTS, CASES, model="chosen-model", api_config=config)
        for kwargs in ({"model": "chosen-model"}, {"api_config": config},
                       {"model": " ", "api_config": config}):
            with self.subTest(kwargs=kwargs), patch.object(
                testgen_api, "generate_one"
            ) as call, self.assertRaises(ValueError):
                evaluate(DOCUMENTS, CASES, **kwargs)
            call.assert_not_called()

    def test_api_abstention_ignores_outer_whitespace_but_keeps_raw_answer(self):
        from raglab import testgen_api
        from raglab.answering import ABSTENTION_ANSWER

        config = testgen_api.configuration("compatible", "http://127.0.0.1:8765")
        case = EvalCase("unknown", "Who won chess?", (), (), should_abstain=True)
        raw = "  " + ABSTENTION_ANSWER + "\n"
        with patch.object(testgen_api, "api_key", return_value="test-key"), patch.object(
            testgen_api, "generate_one", return_value={"raw": raw}
        ):
            report = evaluate(DOCUMENTS, [case], model="chosen-model", api_config=config)
        self.assertEqual(report.cases[0].answer, raw)
        self.assertTrue(report.cases[0].abstained)
        self.assertEqual(report.metrics["unanswerable_abstention_rate"], 1)

    def test_api_candidate_regressions_are_not_hidden(self):
        from raglab import testgen_api

        config = testgen_api.configuration("compatible", "http://127.0.0.1:8765")
        baseline = evaluate(DOCUMENTS, CASES)
        with patch.object(testgen_api, "api_key", return_value="test-key"), patch.object(
            testgen_api, "generate_one", return_value={"raw": "Invented answer. [unknown]"}
        ):
            candidate = evaluate(DOCUMENTS, CASES, model="chosen-model", api_config=config)
        self.assertFalse(compare_reports(baseline.to_dict(), candidate.to_dict())["passed"])
        self.assertEqual(candidate.metrics["faithfulness"], 0)
        self.assertEqual(candidate.metrics["citation_correctness"], 0)
        self.assertTrue(candidate.cases[0].issues)

    def test_gate_supports_minimums_and_maximums(self):
        gate = check_gate(
            {"faithfulness": 1.0, "p95_latency_ms": 12.0},
            {"faithfulness": 0.95, "p95_latency_ms_max": 20.0},
        )
        self.assertTrue(gate["passed"])

    def test_comparison_detects_regression(self):
        baseline = evaluate(DOCUMENTS, CASES).to_dict()
        candidate = deepcopy(baseline)
        self.assertTrue(compare_reports(baseline, candidate)["passed"])
        candidate["metrics"]["faithfulness"] = 0.8
        self.assertFalse(compare_reports(baseline, candidate)["passed"])
        baseline["metrics"]["faithfulness"] = 0.92
        candidate["metrics"]["faithfulness"] = 0.90
        self.assertTrue(compare_reports(baseline, candidate, max_drop=0.02)["passed"])

    def test_gate_uses_unrounded_measurements(self):
        with patch("raglab.evaluation.faithfulness", return_value=0.99996), patch(
            "raglab.evaluation.time.perf_counter", side_effect=[0.0, 0.0500004]
        ):
            report = evaluate(DOCUMENTS, CASES)
        gate = check_gate(report.metrics, {"faithfulness": 1, "p95_latency_ms_max": 50})
        self.assertFalse(gate["passed"])
        self.assertTrue(all(not check["passed"] for check in gate["checks"]))

    def test_gate_fails_closed_on_missing_or_invalid_measurements(self):
        for name, threshold in (("p95_latency_ms_max", 50), ("faithfulness", 0)):
            metric = name.removesuffix("_max")
            for value in (None, float("nan"), float("inf"), -1, True, "0"):
                with self.subTest(name=name, value=value):
                    self.assertFalse(check_gate({metric: value}, {name: threshold})["passed"])
            self.assertFalse(check_gate({}, {name: threshold})["passed"])
        for thresholds in ({}, [], {"faithfulness": float("nan")}, {"faithfulness": True}):
            with self.subTest(thresholds=thresholds), self.assertRaises(ValueError):
                check_gate({}, thresholds)

    def test_abstention_is_separate_from_answer_quality(self):
        unknown = EvalCase("unknown", "Who won chess?", (), (), should_abstain=True)
        report = evaluate(DOCUMENTS, CASES + [unknown])
        self.assertEqual(report.metrics["unanswerable_abstention_rate"], 1.0)
        self.assertEqual(report.metrics["required_phrase_coverage"], 1.0)
        self.assertTrue(report.cases[1].abstained)
        self.assertIsNone(report.cases[1].faithfulness)
        only_unknown = evaluate(DOCUMENTS, [unknown])
        self.assertIsNone(only_unknown.metrics["faithfulness"])
        self.assertFalse(check_gate(only_unknown.metrics, {"faithfulness": 0.9})["passed"])
        wrong_abstention = evaluate(DOCUMENTS, [replace(CASES[0], question="Who won chess?")])
        self.assertEqual(wrong_abstention.metrics["answerable_response_rate"], 0.0)
        self.assertEqual(wrong_abstention.metrics["required_phrase_coverage"], 0.0)
        self.assertTrue(wrong_abstention.cases[0].issues)

    def test_related_missing_information_is_reported_as_a_real_failure(self):
        case = EvalCase("api-owner", "Who owns the API?", (), (), should_abstain=True)
        with patch("raglab.evaluation.generate_extractive_answer",
                   return_value="The API allows 600 requests per minute. [limits]"):
            report = evaluate(DOCUMENTS, [case])
        self.assertEqual(report.metrics["unanswerable_abstention_rate"], 0.0)
        self.assertIn("Expected abstention; returned an answer", report.cases[0].issues)

    def test_multi_source_recall_requires_all_expected_sources(self):
        documents = DOCUMENTS + [Document("refund", "Refunds", "Refunds take 30 days.")]
        case = EvalCase("both", "API requests and refunds?", ("limits", "refund"),
                        ("600 requests per minute", "30 days"))
        report = evaluate(documents, [case], top_k=1)
        self.assertEqual(report.metrics["hit_rate_at_3"], 1.0)
        self.assertEqual(report.metrics["source_recall_at_3"], 0.5)

    def test_comparison_rejects_incompatible_or_invalid_reports(self):
        baseline = evaluate(DOCUMENTS, CASES).to_dict()
        variants = [
            {"metrics": {"faithfulness": 1}},
            {**baseline, "benchmark_sha256": "different"},
            {**baseline, "metrics": {}},
            {**baseline, "metrics": {"faithfulness": 1}},
        ]
        for candidate in variants:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                compare_reports(baseline, candidate)
        for value in (-0.1, float("nan"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compare_reports(baseline, baseline, max_drop=value)
        for value in (None, float("nan"), float("inf")):
            candidate = deepcopy(baseline)
            candidate["metrics"]["faithfulness"] = value
            self.assertFalse(compare_reports(baseline, candidate)["passed"])
        changed = evaluate(DOCUMENTS, [replace(CASES[0], question="What API limits apply?")])
        self.assertNotEqual(baseline["benchmark_sha256"], changed.benchmark_sha256)

    def test_dataset_validation_rejects_broken_labels(self):
        for case in (
            replace(CASES[0], expected_doc_ids=("unknown",)),
            replace(CASES[0], required_facts=("invented fact",)),
            replace(CASES[0], should_abstain=True),
            replace(CASES[0], should_abstain="false"),
            replace(CASES[0], required_facts=()),
        ):
            with self.subTest(case=case), self.assertRaises((ValueError, TypeError)):
                evaluate(DOCUMENTS, [case])
        for documents, cases in ((DOCUMENTS * 2, CASES), (DOCUMENTS, CASES * 2), (DOCUMENTS, [])):
            with self.subTest(documents=documents, cases=cases), self.assertRaises(ValueError):
                evaluate(documents, cases)

    def test_baseline_latency_policy_is_unchanged(self):
        path = Path(__file__).resolve().parents[1] / "config/thresholds.json"
        thresholds = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(thresholds["p95_latency_ms_max"], 50.0)

    def test_llm_threshold_profile_matches_baseline_minus_latency_cap(self):
        config_dir = Path(__file__).resolve().parents[1] / "config"
        baseline = json.loads((config_dir / "thresholds.json").read_text(encoding="utf-8"))
        llm = json.loads((config_dir / "thresholds.llm.json").read_text(encoding="utf-8"))
        self.assertEqual(baseline["p95_latency_ms_max"], 50.0)
        self.assertEqual(llm, {key: value for key, value in baseline.items()
                               if key != "p95_latency_ms_max"})

    def test_expanded_benchmark_and_failure_reports(self):
        root = Path(__file__).resolve().parents[1]
        documents = load_documents(root / "data/corpus.json")
        cases = load_cases(root / "data/eval_cases.jsonl")
        report = evaluate(documents, cases)
        self.assertEqual(len(cases), 56)
        self.assertEqual(sum(case.should_abstain for case in cases), 15)
        self.assertTrue({"boundary_conditions", "missing_info", "multi_source",
                         "incorrect_premise", "conflicting_sources"}
                        <= {case.category for case in cases})
        # Simulate an inappropriate answer so this tests the evaluator, not a permanent model flaw.
        with patch("raglab.evaluation.generate_extractive_answer", return_value="Invented answer."):
            report = evaluate(documents, cases)
        gate = check_gate(report.metrics, {"unanswerable_abstention_rate": 1.0})
        with TemporaryDirectory() as directory:
            json_path, md_path = Path(directory) / "report.json", Path(directory) / "report.md"
            write_json_report(report, json_path, gate)
            write_markdown_report(report, md_path, gate)
            self.assertIn('"passed": false', json_path.read_text(encoding="utf-8"))
            markdown = md_path.read_text(encoding="utf-8")
            self.assertIn("Quality gate: FAIL", markdown)
            self.assertIn("Expected abstention; returned an answer", markdown)


if __name__ == "__main__":
    unittest.main()
