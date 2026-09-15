import json
import os
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import urlopen

from raglab.dashboard import make_server, publish_pytest_run, read_runs, record_run


class DashboardTests(unittest.TestCase):
    def test_history_preserves_snapshots_and_error_outcomes(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "runs.sqlite3"
            self.assertEqual(read_runs(database), [])
            report = {"metrics": {"faithfulness": 0.5}}
            first = record_run(database, report=report, gate={"passed": False})
            report["metrics"]["faithfulness"] = 1
            second = record_run(database, trigger="pytest", error="Evaluator failed",
                                tests={"exit_code": 1, "failed": 1})
            runs = read_runs(database)
            self.assertEqual([run["id"] for run in runs], [second, first])
            self.assertEqual(runs[1]["report"]["metrics"]["faithfulness"], 0.5)
            self.assertFalse(runs[1]["gate"]["passed"])
            self.assertIsNone(runs[0]["report"])
            self.assertEqual(runs[0]["tests"]["failed"], 1)

    def test_api_reflects_new_runs_and_does_not_cache_or_hide_errors(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("<h1>Dashboard</h1>", encoding="utf-8")
            database = root / "runs.sqlite3"
            with make_server(database, port=0, assets=root) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                url = f"http://127.0.0.1:{server.server_port}"
                try:
                    with urlopen(url + "/") as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers["Cache-Control"], "no-store")
                    with urlopen(url + "/api/runs") as response:
                        self.assertEqual(json.load(response), {"schema_version": 1, "runs": []})
                    run_id = record_run(database, gate={"passed": False})
                    with urlopen(url + "/api/runs") as response:
                        self.assertEqual(json.load(response)["runs"][0]["id"], run_id)
                    database.write_bytes(b"not a SQLite database")
                    with self.assertRaises(HTTPError) as error:
                        urlopen(url + "/api/runs")
                    self.assertEqual(error.exception.code, 500)
                finally:
                    server.shutdown()
                    thread.join(timeout=5)

    def test_broken_evaluation_is_a_fresh_error_snapshot(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            record_run(root / "reports/runs.sqlite3", report={"metrics": {"faithfulness": 1}})
            result = publish_pytest_run({"exit_code": 0, "passed": 1}, directory=root)
            self.assertIn("FileNotFoundError", result["error"])
            runs = read_runs(root / "reports/runs.sqlite3")
            self.assertIsNone(runs[0]["report"])
            self.assertIsNone(runs[0]["gate"])
            self.assertEqual(runs[0]["tests"]["passed"], 1)
            self.assertEqual(len(runs), 2)

    def test_real_pytest_hook_preserves_exit_code_and_records_each_session(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "config").mkdir()
            (root / "data/corpus.json").write_text(json.dumps([
                {"id": "refund", "title": "Refund", "text": "Refunds take 30 days."},
            ]), encoding="utf-8")
            (root / "data/eval_cases.jsonl").write_text(json.dumps({
                "id": "refund", "question": "How long do refunds take?",
                "expected_doc_ids": ["refund"], "required_facts": ["30 days"],
            }) + "\n", encoding="utf-8")
            shutil.copyfile(Path(__file__).resolve().parents[1] / "conftest.py", root / "conftest.py")
            environment = {**os.environ, "RAGLAB_SKIP_DASHBOARD": "0",
                           "RAGLAB_RECORD_DASHBOARD": "1"}
            for succeeds, thresholds, expected_exit in (
                (False, {"faithfulness": 1}, 1),
                (True, {"unmeasured_metric": 1}, 0),
            ):
                with self.subTest(succeeds=succeeds):
                    (root / "test_sample.py").write_text(
                        f"def test_sample():\n    assert {succeeds}\n", encoding="utf-8")
                    (root / "config/thresholds.json").write_text(json.dumps(thresholds),
                                                               encoding="utf-8")
                    completed = subprocess.run([
                        sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "test_sample.py",
                    ], cwd=root, env=environment, capture_output=True, text=True, check=False)
                    self.assertEqual(completed.returncode, expected_exit, completed.stdout)
                    self.assertIn("Dashboard recorded run", completed.stdout)
                    run = read_runs(root / "reports/runs.sqlite3")[0]
                    self.assertEqual(run["tests"]["exit_code"], expected_exit)
                    self.assertEqual(run["tests"]["failed"], 0 if succeeds else 1)
                    self.assertEqual(run["tests"]["passed"], 1 if succeeds else 0)
                    self.assertEqual(run["trigger"], "pytest")
                    self.assertEqual(run["gate"]["passed"], not succeeds)
            self.assertEqual(len(read_runs(root / "reports/runs.sqlite3")), 2)

            environment.pop("RAGLAB_RECORD_DASHBOARD")
            before = (root / "reports/runs.sqlite3").read_bytes()
            completed = subprocess.run([
                sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_sample.py",
            ], cwd=root, env=environment, capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stdout)
            self.assertNotIn("Dashboard", completed.stdout)
            self.assertEqual((root / "reports/runs.sqlite3").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
