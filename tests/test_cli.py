import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from raglab.dashboard import read_runs


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
                        "--markdown", str(root / "report.md"),
                    ], capture_output=True, text=True, check=False)
                    self.assertEqual(result.returncode, expected_exit, result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    if expected_exit == 1:
                        payload = json.loads(report.read_text(encoding="utf-8"))
                        self.assertFalse(payload["gate"]["passed"])
                        self.assertIsNone(payload["gate"]["checks"][0]["actual"])
                        self.assertIn("N/A", result.stdout)
                        history = read_runs(root / "runs.sqlite3")
                        self.assertEqual(len(history), 2)
                        self.assertFalse(history[0]["gate"]["passed"])
                        self.assertEqual(history[0]["trigger"], "evaluation")

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


if __name__ == "__main__":
    unittest.main()
