"""Record the test session and a fresh RAG evaluation for the local dashboard."""
import os
import time
from pathlib import Path


def pytest_sessionstart(session):
    session.rag_started_at = time.perf_counter()


def pytest_sessionfinish(session, exitstatus):
    if os.environ.get("RAGLAB_SKIP_DASHBOARD") == "1" or session.config.option.collectonly:
        return
    terminal = session.config.pluginmanager.get_plugin("terminalreporter")
    stats = terminal.stats if terminal else {}
    tests = {
        "exit_code": int(exitstatus), "collected": session.testscollected,
        "passed": len(stats.get("passed", [])), "failed": len(stats.get("failed", [])),
        "skipped": len(stats.get("skipped", [])), "errors": len(stats.get("error", [])),
        "xfailed": len(stats.get("xfailed", [])), "xpassed": len(stats.get("xpassed", [])),
        "duration_seconds": time.perf_counter() - session.rag_started_at,
    }
    try:
        from raglab.dashboard import publish_pytest_run

        result = publish_pytest_run(tests, directory=Path(__file__).resolve().parent)
        status = "ERROR" if result["error"] else "PASS" if result["gate"]["passed"] else "FAIL"
        message = f"Dashboard recorded run #{result['id']} | RAG quality gate: {status}"
        if result["error"]:
            message += f" ({result['error']})"
    except Exception as error:  # noqa: BLE001 - reporting must preserve the original pytest exit code.
        message = f"Dashboard could not record this run: {error}"
    if terminal:
        terminal.write_line("")
        terminal.write_line(message)
