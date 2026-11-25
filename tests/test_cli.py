import contextlib
import io
import itertools
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from raglab import cli, testgen_api


class CliTests(unittest.TestCase):
    def test_gate_exit_codes_and_saved_failure_reason(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            corpus, cases = root / "corpus.json", root / "cases.jsonl"
            thresholds, report = root / "thresholds.json", root / "report.json"
            corpus.write_text(json.dumps([
                {"id": "refund", "title": "Refund", "text": "Refunds take 30 days."},
            ]), encoding="utf-8")
            cases.write_text(json.dumps({
                "id": "refund", "question": "How long do refunds take?",
                "expected_doc_ids": ["refund"], "required_facts": ["30 days"],
            }) + "\n", encoding="utf-8")
            for limits, expected_exit in (
                ({"faithfulness": 1}, 0), ({"missing_latency_ms_max": 50}, 1), ({}, 2),
            ):
                with self.subTest(limits=limits):
                    thresholds.write_text(json.dumps(limits), encoding="utf-8")
                    result = subprocess.run([
                        sys.executable, "-m", "raglab", "evaluate", "--gate",
                        "--corpus", str(corpus), "--cases", str(cases),
                        "--thresholds", str(thresholds), "--report", str(report),
                    ], capture_output=True, text=True, check=False)
                    self.assertEqual(result.returncode, expected_exit, result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    if expected_exit == 1:
                        payload = json.loads(report.read_text(encoding="utf-8"))
                        self.assertFalse(payload["gate"]["passed"])
                        self.assertIsNone(payload["gate"]["checks"][0]["actual"])
                        self.assertIn("N/A", result.stdout)
                    self.assertFalse((root / "runs.sqlite3").exists())
                    self.assertFalse((root / "report.md").exists())

    def test_default_evaluation_prints_results_without_files(self):
        with TemporaryDirectory() as directory:
            result = subprocess.run([
                sys.executable, "-m", "raglab", "evaluate",
            ], cwd=directory, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Quality gate:", result.stdout)
            self.assertIn("Cases needing review", result.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_old_baseline_comparison_is_a_clear_input_error(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "old.json"
            path.write_text('{"metrics": {"faithfulness": 1}}', encoding="utf-8")
            result = subprocess.run([
                sys.executable, "-m", "raglab", "compare", str(path), str(path),
            ], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertIn("schema version 2", result.stderr)
            self.assertNotIn("Traceback", result.stderr)


class EvaluateModelTests(unittest.TestCase):
    def _write_dataset(self, root: Path):
        corpus, cases = root / "corpus.json", root / "cases.jsonl"
        corpus.write_text(json.dumps([
            {"id": "refund", "title": "Refund", "text": "Refunds take 30 days."},
        ]), encoding="utf-8")
        cases.write_text(json.dumps({
            "id": "refund", "question": "How long do refunds take?",
            "expected_doc_ids": ["refund"], "required_facts": ["30 days"],
        }) + "\n", encoding="utf-8")
        return corpus, cases

    def _evaluate(self, *arguments):
        args = cli.build_parser().parse_args(["evaluate", *[str(a) for a in arguments]])
        with contextlib.redirect_stdout(io.StringIO()):
            return cli._run(args)

    def _model_flags(self):
        return [
            "--model", "refund-model", "--provider", "compatible",
            "--base-url", "http://127.0.0.1:9/v1",
            "--api-key-env", "TEST_ONLY_KEY",
        ]

    def test_model_answer_is_recorded_with_llm_generator_and_provider(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            corpus, cases = self._write_dataset(root)
            thresholds, report = root / "thresholds.json", root / "report.json"
            thresholds.write_text(json.dumps({"faithfulness": 0}), encoding="utf-8")
            options = root / "options.json"
            options.write_text(json.dumps({"max_tokens": 64}), encoding="utf-8")
            with (
                patch.object(testgen_api, "api_key", return_value="test-only-key"),
                patch.object(testgen_api, "generate_one", return_value={
                    "raw": "Refunds take 30 days. [refund]",
                    "returned_model": "refund-model",
                }) as generate,
            ):
                self._evaluate(
                    *self._model_flags(), "--api-options", options,
                    "--corpus", corpus, "--cases", cases,
                    "--thresholds", thresholds, "--report", report,
                )
            generate.assert_called_once()
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["config"]["generator"], "llm-replay")
            self.assertEqual(payload["config"]["model"], "refund-model")
            self.assertEqual(payload["config"]["api"]["provider"], "compatible")
            self.assertEqual(payload["config"]["api"]["options"]["max_tokens"], 64)
            self.assertEqual(
                payload["cases"][0]["answer"], "Refunds take 30 days. [refund]")

    def test_gate_thresholds_apply_to_model_runs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            corpus, cases = self._write_dataset(root)
            thresholds, report = root / "thresholds.json", root / "report.json"
            generations = report.with_suffix(".generations.jsonl")
            for limits, exit_code in (
                ({"faithfulness": 1}, None), ({"p95_latency_ms_max": 0}, 1),
            ):
                with self.subTest(limits=limits):
                    thresholds.write_text(json.dumps(limits), encoding="utf-8")
                    report.unlink(missing_ok=True)
                    generations.unlink(missing_ok=True)
                    arguments = [
                        *self._model_flags(),
                        "--corpus", corpus, "--cases", cases,
                        "--thresholds", thresholds, "--report", report, "--gate",
                    ]
                    with (
                        patch.object(testgen_api, "api_key",
                                     return_value="test-only-key"),
                        patch.object(testgen_api, "generate_one", return_value={
                            "raw": "Refunds take 30 days. [refund]"}),
                        patch("raglab.saved_eval_generate.time.perf_counter",
                              side_effect=itertools.count(step=0.001)),
                    ):
                        if exit_code is None:
                            self._evaluate(*arguments)
                        else:
                            with self.assertRaises(SystemExit) as caught:
                                self._evaluate(*arguments)
                            self.assertEqual(caught.exception.code, exit_code)
                    payload = json.loads(report.read_text(encoding="utf-8"))
                    self.assertEqual(payload["schema_version"], 2)
                    self.assertEqual(payload["gate"]["passed"], exit_code is None)

    def test_generation_error_aborts_without_writing_report(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            corpus, cases = self._write_dataset(root)
            thresholds, report = root / "thresholds.json", root / "report.json"
            thresholds.write_text(json.dumps({"faithfulness": 0}), encoding="utf-8")
            with (
                patch.object(testgen_api, "api_key", return_value="test-only-key"),
                patch.object(testgen_api, "generate_one", return_value={
                    "raw": "Refunds take 30 days. [refund]",
                    "generation_error": "truncated",
                }),
                self.assertRaises(ValueError),
            ):
                self._evaluate(
                    *self._model_flags(),
                    "--corpus", corpus, "--cases", cases,
                    "--thresholds", thresholds, "--report", report,
                )
            self.assertFalse(report.exists())

    def test_empty_thresholds_rejected_before_any_model_call(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            corpus, cases = self._write_dataset(root)
            thresholds = root / "thresholds.json"
            thresholds.write_text("{}", encoding="utf-8")
            with (
                patch.object(testgen_api, "api_key", return_value="test-only-key"),
                patch.object(testgen_api, "generate_one") as generate,
                self.assertRaises(ValueError),
            ):
                self._evaluate(
                    *self._model_flags(),
                    "--corpus", corpus, "--cases", cases,
                    "--thresholds", thresholds,
                )
            generate.assert_not_called()

    def test_model_options_are_rejected_without_model(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            corpus, cases = self._write_dataset(root)
            thresholds = root / "thresholds.json"
            thresholds.write_text(json.dumps({"faithfulness": 0}), encoding="utf-8")
            options = root / "options.json"
            options.write_text("{}", encoding="utf-8")
            for extra in (
                ["--provider", "openai"],
                ["--base-url", "https://example.invalid/v1"],
                ["--api-key-env", "TEST_ONLY_KEY"],
                ["--api-options", str(options)],
            ):
                with (
                    self.subTest(extra=extra),
                    self.assertRaisesRegex(ValueError, "API options require --model"),
                ):
                    self._evaluate(
                        *extra, "--corpus", corpus, "--cases", cases,
                        "--thresholds", thresholds,
                    )

    def test_evaluate_without_model_never_touches_the_api(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            corpus, cases = self._write_dataset(root)
            thresholds, report = root / "thresholds.json", root / "report.json"
            thresholds.write_text(json.dumps({"faithfulness": 0}), encoding="utf-8")
            with (
                patch.object(testgen_api, "api_key",
                             side_effect=AssertionError("key lookup")) as key,
                patch.object(testgen_api, "generate_one",
                             side_effect=AssertionError("network")) as generate,
            ):
                self._evaluate(
                    "--corpus", corpus, "--cases", cases,
                    "--thresholds", thresholds, "--report", report,
                )
            key.assert_not_called()
            generate.assert_not_called()
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["config"]["generator"], "extractive")

    def test_generate_records_once_and_replays_without_credentials(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            corpus, cases = self._write_dataset(root)
            generations = root / "generations.jsonl"
            arguments = cli.build_parser().parse_args([
                str(argument) for argument in (
                    "generate", "--model", "refund-model", "--provider", "compatible",
                    "--base-url", "http://127.0.0.1:9/v1", "--api-key-env", "TEST_ONLY_KEY",
                    "--corpus", corpus, "--cases", cases, "--output", generations,
                )
            ])
            with (
                contextlib.redirect_stdout(io.StringIO()),
                patch.object(testgen_api, "api_key", return_value="test-only-key"),
                patch.object(testgen_api, "generate_one",
                             return_value={"raw": "Refunds take 30 days. [refund]"}),
            ):
                cli._run(arguments)
            before = generations.read_text(encoding="utf-8")
            with (
                contextlib.redirect_stdout(io.StringIO()),
                patch.object(testgen_api, "api_key", return_value="test-only-key"),
                patch.object(testgen_api, "generate_one",
                             return_value={"raw": "Refunds take 30 days. [refund]"}),
                self.assertRaises(FileExistsError),
            ):
                cli._run(arguments)
            self.assertEqual(generations.read_text(encoding="utf-8"), before)
            thresholds, report = root / "thresholds.json", root / "report.json"
            thresholds.write_text(json.dumps({"faithfulness": 0}), encoding="utf-8")
            with (
                patch.object(testgen_api, "api_key",
                             side_effect=AssertionError("key lookup")),
                patch.object(testgen_api, "generate_one",
                             side_effect=AssertionError("network")),
            ):
                self._evaluate(
                    "--generations", generations,
                    "--corpus", corpus, "--cases", cases,
                    "--thresholds", thresholds, "--report", report,
                )
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["config"]["generator"], "llm-replay")
            self.assertEqual(payload["config"]["model"], "refund-model")
            self.assertEqual(
                payload["cases"][0]["answer"], "Refunds take 30 days. [refund]")

    def test_generate_exits_nonzero_on_failed_generation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            corpus, cases = self._write_dataset(root)
            generations = root / "generations.jsonl"
            arguments = cli.build_parser().parse_args([
                str(argument) for argument in (
                    "generate", "--model", "refund-model", "--provider", "compatible",
                    "--base-url", "http://127.0.0.1:9/v1", "--api-key-env", "TEST_ONLY_KEY",
                    "--corpus", corpus, "--cases", cases, "--output", generations,
                )
            ])
            with (
                contextlib.redirect_stdout(io.StringIO()),
                patch.object(testgen_api, "api_key", return_value="test-only-key"),
                patch.object(testgen_api, "generate_one", return_value={
                    "raw": "answer", "generation_error": "truncated"}),
                self.assertRaises(SystemExit) as caught,
            ):
                cli._run(arguments)
            self.assertEqual(caught.exception.code, 1)
            rows = [json.loads(line) for line in
                    generations.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["generation"]["generation_error"], "truncated")

    def test_evaluate_model_requires_report_to_keep_paid_evidence(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            corpus, cases = self._write_dataset(root)
            thresholds = root / "thresholds.json"
            thresholds.write_text(json.dumps({"faithfulness": 0}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "--report"):
                self._evaluate(
                    *self._model_flags(),
                    "--corpus", corpus, "--cases", cases,
                    "--thresholds", thresholds,
                )

    def test_replay_rejects_live_api_flags(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            corpus, cases = self._write_dataset(root)
            thresholds = root / "thresholds.json"
            thresholds.write_text(json.dumps({"faithfulness": 0}), encoding="utf-8")
            generations = root / "generations.jsonl"
            generations.write_text("{}\n", encoding="utf-8")
            options = root / "options.json"
            options.write_text("{}", encoding="utf-8")
            for extra in (
                ["--provider", "openai"],
                ["--base-url", "https://example.invalid/v1"],
                ["--api-key-env", "TEST_ONLY_KEY"],
                ["--api-options", str(options)],
            ):
                with (
                    self.subTest(extra=extra),
                    self.assertRaisesRegex(ValueError, "API options require --model"),
                ):
                    self._evaluate(
                        "--generations", generations, *extra,
                        "--corpus", corpus, "--cases", cases,
                        "--thresholds", thresholds,
                    )
            with self.assertRaises(SystemExit):
                cli.build_parser().parse_args([
                    "evaluate", "--model", "x", "--generations", str(generations)])

    def test_replay_report_never_overwrites_generations_or_existing_report(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            corpus, cases = self._write_dataset(root)
            thresholds = root / "thresholds.json"
            thresholds.write_text(json.dumps({"faithfulness": 0}), encoding="utf-8")
            generations = root / "generations.jsonl"
            generations.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "--report must not overwrite"):
                self._evaluate(
                    "--generations", generations, "--report", generations,
                    "--corpus", corpus, "--cases", cases,
                    "--thresholds", thresholds,
                )
            self.assertEqual(generations.read_text(encoding="utf-8"), "{}\n")
            report = root / "report.json"
            report.write_text('{"kept": true}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Refusing to overwrite existing file"):
                self._evaluate(
                    "--generations", generations, "--report", report,
                    "--corpus", corpus, "--cases", cases,
                    "--thresholds", thresholds,
                )
            self.assertEqual(report.read_text(encoding="utf-8"), '{"kept": true}')

    def test_model_and_replay_runs_require_explicit_thresholds(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            corpus, cases = self._write_dataset(root)
            generations = root / "missing.jsonl"
            report = root / "report.json"
            with (
                patch.object(testgen_api, "api_key",
                             side_effect=AssertionError("key lookup")) as key,
                patch.object(testgen_api, "generate_one",
                             side_effect=AssertionError("network")) as generate,
                self.assertRaisesRegex(ValueError, "require explicit --thresholds"),
            ):
                self._evaluate(
                    *self._model_flags(),
                    "--corpus", corpus, "--cases", cases, "--report", report,
                )
            key.assert_not_called()
            generate.assert_not_called()
            self.assertFalse(report.exists())
            self.assertFalse(report.with_suffix(".generations.jsonl").exists())
            with self.assertRaisesRegex(ValueError, "require explicit --thresholds"):
                self._evaluate(
                    "--generations", generations,
                    "--corpus", corpus, "--cases", cases, "--report", report,
                )
            self.assertFalse(report.exists())

    def test_replay_accepts_explicit_baseline_or_llm_thresholds(self):
        root = Path(__file__).resolve().parents[1]
        fixture = root / "reports/rag/fixture"
        with TemporaryDirectory() as directory:
            for name in ("thresholds.json", "thresholds.llm.json"):
                with self.subTest(thresholds=name):
                    report = Path(directory) / f"{name}.report.json"
                    self._evaluate(
                        "--generations", fixture / "generations.jsonl",
                        "--corpus", fixture / "corpus.json",
                        "--cases", fixture / "cases.jsonl",
                        "--thresholds", root / "config" / name,
                        "--report", report, "--gate",
                    )
                    payload = json.loads(report.read_text(encoding="utf-8"))
                    self.assertTrue(payload["gate"]["passed"])
                    self.assertEqual(payload["config"]["generator"], "llm-replay")

    def test_report_must_not_overwrite_corpus(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            corpus, cases = self._write_dataset(root)
            thresholds = root / "thresholds.json"
            thresholds.write_text(json.dumps({"faithfulness": 0}), encoding="utf-8")
            before = corpus.read_text(encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "--report must not overwrite"):
                self._evaluate(
                    "--corpus", corpus, "--cases", cases,
                    "--thresholds", thresholds, "--report", corpus,
                )
            self.assertEqual(corpus.read_text(encoding="utf-8"), before)


class CompareTests(unittest.TestCase):
    def _reports(self, root: Path):
        corpus, cases = root / "corpus.json", root / "cases.jsonl"
        corpus.write_text(json.dumps([
            {"id": "refund", "title": "Refund", "text": "Refunds take 30 days."},
        ]), encoding="utf-8")
        cases.write_text(json.dumps({
            "id": "refund", "question": "How long do refunds take?",
            "expected_doc_ids": ["refund"], "required_facts": ["30 days"],
        }) + "\n", encoding="utf-8")
        baseline = root / "baseline.json"
        args = cli.build_parser().parse_args([
            "evaluate", "--corpus", str(corpus), "--cases", str(cases),
            "--report", str(baseline)])
        with contextlib.redirect_stdout(io.StringIO()):
            cli._run(args)
        return baseline

    def _compare(self, *arguments):
        args = cli.build_parser().parse_args(["compare", *[str(a) for a in arguments]])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            cli._run(args)
        return output.getvalue()

    def test_nway_compare_preserves_order_and_exports_named_changes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self._reports(root)
            same = root / "same.json"
            same.write_text(baseline.read_text(encoding="utf-8"), encoding="utf-8")
            bad = root / "bad.json"
            bad.write_text(baseline.read_text(encoding="utf-8"), encoding="utf-8")
            payload = json.loads(bad.read_text(encoding="utf-8"))
            payload["cases"][0]["answer"] = "I could not find supporting context."
            payload["metrics"]["faithfulness"] = 0
            payload["metrics"]["required_phrase_coverage"] = 0
            payload["metrics"]["citation_correctness"] = 0
            bad.write_text(json.dumps(payload), encoding="utf-8")
            exported = root / "comparison.json"
            with self.assertRaises(SystemExit) as caught:
                self._compare(baseline, same, bad, "--output", exported)
            self.assertEqual(caught.exception.code, 1)
            result = json.loads(exported.read_text(encoding="utf-8"))
            self.assertFalse(result["passed"])
            names = [candidate["name"] for candidate in result["candidates"]]
            self.assertEqual(names, [str(same.resolve()), str(bad.resolve())])
            self.assertTrue(result["candidates"][0]["passed"])
            self.assertFalse(result["candidates"][1]["passed"])
            self.assertEqual(result["candidates"][0]["config"]["generator"], "extractive")
            change = result["candidates"][1]["case_changes"][0]
            self.assertEqual(change["disposition"], "answer -> abstain")
            self.assertEqual(change["lost_phrases"], ["30 days"])
            self.assertEqual(change["lost_citations"], ["refund"])

    def test_failing_candidate_exits_one_and_prints_case_changes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self._reports(root)
            bad = root / "bad.json"
            payload = json.loads(baseline.read_text(encoding="utf-8"))
            payload["cases"][0]["answer"] = "I could not find supporting context."
            payload["metrics"]["faithfulness"] = 0
            bad.write_text(json.dumps(payload), encoding="utf-8")
            stream = io.StringIO()
            with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(stream):
                cli._run(cli.build_parser().parse_args(
                    ["compare", str(baseline), str(bad)]))
            self.assertEqual(caught.exception.code, 1)
            output = stream.getvalue()
            self.assertIn("FAIL", output)
            self.assertIn("answer -> abstain", output)
            self.assertIn("30 days", output)

    def test_output_never_overwrites_inputs_or_existing_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self._reports(root)
            candidate = root / "candidate.json"
            candidate.write_text(baseline.read_text(encoding="utf-8"), encoding="utf-8")
            before = baseline.read_bytes()
            with self.assertRaisesRegex(ValueError, "--output must not overwrite"):
                self._compare(baseline, candidate, "--output", baseline)
            self.assertEqual(baseline.read_bytes(), before)
            existing = root / "existing.json"
            existing.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Refusing to overwrite existing file"):
                self._compare(baseline, candidate, "--output", existing)
            self.assertEqual(existing.read_text(encoding="utf-8"), "{}")

    def test_two_file_compare_remains_valid(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = self._reports(root)
            candidate = root / "candidate.json"
            candidate.write_text(baseline.read_text(encoding="utf-8"), encoding="utf-8")
            output = self._compare(baseline, candidate)
            self.assertIn("PASS", output)


if __name__ == "__main__":
    unittest.main()
