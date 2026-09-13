import json
import subprocess
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from raglab import testgen
from raglab.testgen_view import render_html
from raglab.testgen_worker import check_value


class TestGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = testgen.load_tasks()

    def records(self, task=None):
        task = task or self.tasks[0]
        records = []
        for condition in testgen.CONDITIONS:
            record = testgen.record_for(
                task, condition, testgen.digest(self.tasks), "fixture", None, "reference_fixture"
            )
            record["raw"] = json.dumps({"tests": task["reference_tests"]})
            records.append(record)
        return records

    def test_reference_suite_detects_seeded_bugs(self):
        report = testgen.evaluate(self.tasks, self.records())
        for result in report["summary"].values():
            self.assertEqual(result["mutants_killed"], 2)
            self.assertEqual(result["valid"], 1)
        self.assertEqual(report["paired_deltas"][0]["docs_minus_code"], 0)

    def test_one_false_assertion_disqualifies_entire_suite(self):
        records = self.records()
        for record in records:
            cases = deepcopy(self.tasks[0]["reference_tests"])
            cases.append({"args": [5, 0, 10], "expected": 999})
            record["raw"] = json.dumps({"tests": cases})
        report = testgen.evaluate(self.tasks, records)
        for result in report["summary"].values():
            self.assertEqual(result["false_alarm"], 1)
            self.assertEqual(result["mutants_killed"], 0)
            self.assertEqual(result["mutants_total"], 2)

    def test_malformed_generation_stays_in_denominator(self):
        records = self.records()
        records[0]["raw"] = "Here is some Python: assert target(5, 0, 10) == 5"
        report = testgen.evaluate(self.tasks, records)
        self.assertEqual(report["summary"]["code_only"]["invalid_generation"], 1)
        self.assertEqual(report["summary"]["code_only"]["mutation_score"], 0)

    def test_provider_errors_are_separate_from_invalid_model_output(self):
        records = self.records()
        records[0]["generation_error"] = "HTTP Error 500"
        records[0]["raw"] = ""
        report = testgen.evaluate(self.tasks, records)
        self.assertEqual(report["summary"]["code_only"]["generation_error"], 1)
        self.assertEqual(report["summary"]["code_only"]["invalid_generation"], 0)
        self.assertEqual(report["summary"]["code_only"]["mutation_score"], 0)

    def test_rejects_unpaired_duplicate_and_changed_provenance(self):
        records = self.records()
        variants = [records[:1], records + records[:1]]
        for field, value in (
            ("dataset_sha256", "stale"), ("prompt", "changed"),
            ("model", "different-model"), ("options", {"seed": 123}),
        ):
            changed = deepcopy(records)
            changed[0][field] = value
            variants.append(changed)
        for variant in variants:
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                testgen.evaluate(self.tasks, variant)

    def test_generation_bounds_and_nonfinite_numbers(self):
        invalid = [
            '{"tests":[]}',
            '{"tests":[{"args":[],"expected":NaN}]}',
            '{"tests":[{"args":[],"expected":1e999}]}',
            '{"tests":[{"args":[],"expected":1,"raises":"ValueError"}]}',
            '{"tests":[{"args":[],"raises":"SystemExit"}]}',
            json.dumps({"tests": [{"args": [list(range(101))], "expected": 0}]}),
            json.dumps({"tests": [{"args": [1_000_001], "expected": 0}]}),
            json.dumps({"tests": [{"args": [], "expected": 0}] * 13}),
        ]
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                testgen.parse_generation(raw)
        with self.assertRaises(ValueError):
            check_value(10 ** 1000)

    def test_v1_evidence_remains_replayable_and_protocols_cannot_mix(self):
        records = self.records()
        task = self.tasks[0]
        for record in records:
            old = testgen.record_for(task, record["condition"], testgen.digest(self.tasks),
                                    "fixture", None, "reference_fixture", "testgen-v1")
            old["raw"] = record["raw"]
            old.pop("format")
            record.clear()
            record.update(old)
        report = testgen.evaluate(self.tasks, records)
        self.assertEqual(report["version"], "testgen-v1")
        self.assertEqual(report["summary"]["code_only"]["mutants_killed"], 2)
        with self.assertRaises(ValueError):
            testgen.evaluate(self.tasks, [records[0], self.records()[1]])

    def test_v2_enforces_budget_and_saved_schema(self):
        records = self.records()
        records[0]["source"] = records[1]["source"] = "ollama"
        report = testgen.evaluate(self.tasks, records)
        self.assertEqual(report["summary"]["code_only"]["invalid_generation"], 1)
        records[0]["format"] = "json"
        with self.assertRaises(ValueError):
            testgen.evaluate(self.tasks, records)

    def test_paired_bootstrap_uses_task_differences(self):
        result = testgen.paired_comparison([0.5] * 16)
        self.assertEqual(result["mean_docs_minus_code"], 0.5)
        self.assertEqual(result["task_bootstrap_95_ci"], [0.5, 0.5])
        result = testgen.paired_comparison([-1, 0, 1])
        self.assertEqual(result["docs_wins"], 1)
        self.assertEqual(result["code_wins"], 1)
        self.assertEqual(result["ties"], 1)
        self.assertEqual(result, testgen.paired_comparison([-1, 0, 1]))

    def test_heldout_run_requires_complete_unchanged_plan(self):
        selected = [task for task in self.tasks if task["split"] == "test"]
        plan = {"configuration": testgen.make_plan(self.tasks, "model", "abc")}
        with TemporaryDirectory() as directory:
            output = Path(directory) / "heldout.jsonl"
            with patch.object(testgen, "local_model_digest", return_value="abc"), \
                    patch.object(testgen, "api", return_value={}):
                with self.assertRaisesRegex(ValueError, "requires --plan"):
                    testgen.generate(self.tasks, selected, output, "model", "http://localhost")
                with self.assertRaisesRegex(ValueError, "Frozen plan differs"):
                    testgen.generate(self.tasks, selected[:1], output, "model",
                                     "http://localhost", plan=plan)
                plan["configuration"]["options"] = {"seed": 123}
                with self.assertRaisesRegex(ValueError, "Frozen plan differs"):
                    testgen.generate(self.tasks, selected, output, "model",
                                     "http://localhost", plan=plan)
            self.assertFalse(output.exists())

    def test_report_escapes_model_output_and_labels_fixture(self):
        report = testgen.evaluate(self.tasks, self.records())
        report["model"] = '<script>alert("model")</script>'
        report["rows"][0]["raw"] = '<img src=x onerror="alert(1)">'
        result = render_html(report)
        self.assertNotIn("<script>", result)
        self.assertNotIn("<img ", result)
        self.assertIn("&lt;script&gt;", result)
        self.assertIn("Reference fixture: no LLM was used", result)
        self.assertIn("<details>", result)
        self.assertIn("Inspect evidence", result)

    def test_current_schema_explicitly_supports_json_values_and_arity(self):
        schema = testgen.schema_for(self.tasks[0])
        self.assertIn("number", schema["$defs"]["value"]["type"])
        for variant in schema["properties"]["tests"]["items"]["oneOf"]:
            self.assertEqual(variant["properties"]["args"]["minItems"], 3)
            self.assertEqual(variant["properties"]["args"]["maxItems"], 3)
        positional = {"code": "def target(value, /): return value"}
        arguments = testgen.schema_for(positional)["properties"]["tests"]["items"]["oneOf"][0]
        self.assertEqual(arguments["properties"]["args"]["minItems"], 1)

    def test_qwen_inference_settings_are_explicit_and_do_not_change_llama_defaults(self):
        settings = testgen.inference_settings("qwen3.5:4b")
        self.assertFalse(settings["think"])
        self.assertEqual(settings["options"]["presence_penalty"], 0)
        self.assertEqual(settings["options"]["repeat_penalty"], 1.0)
        self.assertNotIn("presence_penalty", testgen.OPTIONS)
        self.assertNotIn("think", testgen.inference_settings("llama3.1:8b"))

    def test_json_text_is_data_and_boolean_is_not_integer(self):
        text = "__import__('os').system('SHOULD_NOT_RUN')"
        result = testgen.run_suite(
            "def target(value):\n    return value\n",
            [{"args": [text], "expected": text}, {"args": [1], "expected": True}],
        )
        self.assertTrue(result["outcomes"][0]["passed"])
        self.assertFalse(result["outcomes"][1]["passed"])

    def test_expected_exception_and_wrong_exception(self):
        result = testgen.run_suite(
            "def target():\n    raise ValueError('bad')\n",
            [{"args": [], "raises": "ValueError"}, {"args": [], "raises": "TypeError"}],
        )
        self.assertEqual([case["passed"] for case in result["outcomes"]], [True, False])

    def test_timeout_and_worker_failure_are_not_bug_kills(self):
        records = self.records()
        results = [
            {"outcomes": [{"passed": True}]}, {"error": "Execution timeout"},
            {"error": "Worker crashed"},
        ] * 2
        with patch.object(testgen, "run_suite", side_effect=results):
            report = testgen.evaluate(self.tasks, records)
        self.assertEqual(report["summary"]["code_only"]["execution_error"], 1)
        self.assertEqual(report["summary"]["code_only"]["mutants_killed"], 0)
        timed_out = testgen.run_suite(
            "def target():\n    while True:\n        pass\n",
            [{"args": [], "expected": None}], timeout=0.2,
        )
        self.assertEqual(timed_out["error"], "Execution timeout")

    def test_worker_isolated_launch_and_clean_working_directory(self):
        with patch.object(testgen.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, b'{"outcomes":[]}')
            testgen.run_suite("def target(): return 1", [{"args": [], "expected": 1}])
        self.assertEqual(run.call_args.args[0][1:3], ["-I", "-S"])
        self.assertEqual(run.call_args.kwargs["timeout"], 3)
        self.assertFalse(Path(run.call_args.kwargs["cwd"]).exists())
        self.assertNotIn("PATH", run.call_args.kwargs["env"])

    def test_prompts_keep_oracles_and_mutants_out(self):
        for task in self.tasks:
            code_prompt = testgen.prompt_for(task, "code_only")
            docs_prompt = testgen.prompt_for(task, "code_docs")
            self.assertNotIn(task["docs"], code_prompt)
            self.assertEqual(docs_prompt, code_prompt + "\nDocumentation:\n" + task["docs"])
            for mutant in task["mutants"]:
                self.assertNotIn(mutant["code"], docs_prompt)
            self.assertNotIn(testgen.encoded(task["reference_tests"]), docs_prompt)

    def test_saved_report_labels_reference_fixture(self):
        report = testgen.evaluate(self.tasks, self.records())
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            testgen.write_report(report, path)
            self.assertEqual(json.loads(path.read_text())["source"], "reference_fixture")
            self.assertIn("no LLM was used", path.with_suffix(".md").read_text(encoding="utf-8"))

    def test_ollama_pair_records_real_metadata_and_rejects_overwrite(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "generations.jsonl"
            raw = json.dumps({"tests": self.tasks[0]["reference_tests"]})
            response = {"message": {"content": raw}, "done": True,
                        "prompt_eval_count": 100, "eval_count": 20, "done_reason": "stop"}
            with patch.object(testgen, "local_model_digest", return_value="abc"), \
                    patch.object(testgen, "api", return_value=response) as api:
                testgen.generate(self.tasks, self.tasks[:1], output, "model", "http://localhost")
                with self.assertRaises(FileExistsError):
                    testgen.generate(self.tasks, self.tasks[:1], output, "model", "http://localhost")
            records = [json.loads(line) for line in output.read_text().splitlines()]
            chat_calls = [call for call in api.call_args_list if call.args[1] == "/api/chat"]
            self.assertEqual(len(chat_calls), 2)
            self.assertEqual(records[0]["model_digest"], "abc")
            self.assertEqual(records[1]["prompt_tokens"], 100)
            self.assertEqual(records[0]["source"], "ollama")
            self.assertEqual(records[0]["condition"], "code_only")
            self.assertEqual(records[1]["condition"], "code_docs")

    def test_model_change_invalidates_but_preserves_raw_evidence(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "generations.jsonl"
            raw = json.dumps({"tests": self.tasks[0]["reference_tests"]})
            response = {"message": {"content": raw}, "done": True}
            with (
                patch.object(testgen, "local_model_digest", side_effect=["before", "after"]),
                patch.object(testgen, "api", return_value=response),
                self.assertRaisesRegex(ValueError, "preserved and invalidated"),
            ):
                testgen.generate(self.tasks, self.tasks[:1], output, "model", "http://localhost")
            records = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["raw"], raw)
            report = testgen.evaluate(self.tasks, records)
            self.assertEqual(report["summary"]["code_only"]["generation_error"], 1)
            self.assertEqual(report["summary"]["code_only"]["mutants_killed"], 0)
