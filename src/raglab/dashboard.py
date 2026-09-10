from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from raglab.settings import PROJECT_ROOT

DEFAULT_DATABASE = PROJECT_ROOT / "reports" / "runs.sqlite3"
DEFAULT_ASSETS = PROJECT_ROOT / "dashboard" / "dist"


def record_run(
    database: Path = DEFAULT_DATABASE, *, trigger: str = "evaluation",
    report: dict | None = None, gate: dict | None = None,
    tests: dict | None = None, error: str | None = None,
) -> int:
    """Keep complete immutable run snapshots; SQLite serializes concurrent writers."""
    payload = json.dumps({"report": report, "gate": gate, "tests": tests, "error": error},
                         allow_nan=False)
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database, timeout=10)) as connection, connection:
        connection.execute("CREATE TABLE IF NOT EXISTS runs ("
                           "id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, "
                           "trigger TEXT NOT NULL, payload TEXT NOT NULL)")
        cursor = connection.execute(
            "INSERT INTO runs (created_at, trigger, payload) VALUES (?, ?, ?)",
            (datetime.now(UTC).isoformat(), trigger, payload),
        )
        return cursor.lastrowid


def read_runs(database: Path = DEFAULT_DATABASE) -> list[dict[str, Any]]:
    if not Path(database).exists():
        return []
    with closing(sqlite3.connect(database, timeout=10)) as connection:
        rows = connection.execute(
            "SELECT id, created_at, trigger, payload FROM runs ORDER BY id DESC LIMIT 100"
        ).fetchall()
    return [{"id": row[0], "created_at": row[1], "trigger": row[2], **json.loads(row[3])}
            for row in rows]


def publish_pytest_run(tests: dict, *, directory: Path = PROJECT_ROOT) -> dict:
    """A broken evaluator gets a new error snapshot, never a copied previous success."""
    report = gate = error = None
    try:
        from raglab.data import load_cases, load_documents
        from raglab.evaluation import (
            check_gate,
            evaluate,
            write_json_report,
            write_markdown_report,
        )

        result = evaluate(load_documents(directory / "data/corpus.json"),
                          load_cases(directory / "data/eval_cases.jsonl"))
        thresholds = json.loads((directory / "config/thresholds.json").read_text(encoding="utf-8"))
        gate = check_gate(result.metrics, thresholds)
        write_json_report(result, directory / "reports/latest.json", gate)
        write_markdown_report(result, directory / "reports/latest.md", gate)
        report = result.to_dict()
    except Exception as exception:  # noqa: BLE001 - a broken evaluator must become an error snapshot.
        report = gate = None
        error = f"{type(exception).__name__}: {exception}"
    run_id = record_run(directory / "reports/runs.sqlite3", trigger="pytest", report=report,
                        gate=gate, tests=tests, error=error)
    return {"id": run_id, "gate": gate, "error": error}


def make_server(
    database: Path = DEFAULT_DATABASE, *, port: int = 8766, assets: Path = DEFAULT_ASSETS,
) -> ThreadingHTTPServer:
    if not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535")
    if not (assets / "index.html").is_file():
        raise FileNotFoundError(f"Dashboard assets are missing: {assets}")

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(*args, directory=str(assets), **kwargs)

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            super().end_headers()

        def do_GET(self) -> None:
            if urlsplit(self.path).path != "/api/runs":
                super().do_GET()
                return
            try:
                data = {"schema_version": 1, "runs": read_runs(database)}
                body = json.dumps(data, allow_nan=False).encode("utf-8")
                status = 200
            except (sqlite3.Error, OSError, ValueError) as exception:
                body = json.dumps({"error": f"Cannot read run history: {exception}"}).encode("utf-8")
                status = 500
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            pass  # Avoid a terminal log line on every dashboard poll.

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve_dashboard(database: Path = DEFAULT_DATABASE, *, port: int = 8766) -> None:
    with make_server(database, port=port) as server:
        print(f"Dashboard: http://127.0.0.1:{server.server_port}/", flush=True)
        print("Results update after evaluation and pytest runs. Press Ctrl+C to stop.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
