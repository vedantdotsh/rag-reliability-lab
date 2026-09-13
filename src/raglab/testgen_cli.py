"""Subscription CLI transport. Fresh prompt-only sessions, with tool use disqualified."""
import json
import os
import queue
import subprocess
import tempfile
import threading
import time

PREFIX = (
    "This is a prompt-only benchmark. Apply Ponytail: the smallest correct test data. "
    "Do not use any tools, read or write files, run commands, browse, use MCP, or delegate. "
    "All information is in this prompt. Return only the requested JSON as your final answer.\n\n"
)


def cli_prompt(prompt):
    return PREFIX + prompt


def configuration(provider, cli_version, effort="medium"):
    if provider not in ("codex", "cursor"):
        raise ValueError("Unknown CLI provider")
    return {"provider": provider, "cli_version": cli_version, "protocol": "cli-v1",
            "reasoning_effort": effort if provider == "codex" else "selected model variant",
            "sampling": "CLI defaults; no native output schema", "timeout_seconds": 240,
            "session": "fresh empty working directory; no resume",
            "tool_policy": "prompt prohibits tools; observed tool calls disqualify the suite"}


def normalize_cli(provider, events, returncode=0):
    result = {"raw": "", "prompt_tokens": None, "prompt_cached_tokens": None,
              "completion_tokens": None, "reasoning_tokens": None, "returned_model": None,
              "done_reason": None}
    failed, used_tools, finished = returncode != 0, False, False
    messages = []
    for event in events:
        kind = event.get("type")
        if provider == "cursor":
            if kind == "system" and event.get("subtype") == "init":
                result["returned_model"] = event.get("model")
            if kind == "tool_call":
                used_tools = True
            if kind == "result":
                finished = event.get("subtype") == "success" and not event.get("is_error")
                failed |= not finished
                result.update(raw=event.get("result") or "", done_reason=event.get("subtype"),
                              response_id=event.get("request_id"), session_id=event.get("session_id"))
                usage = event.get("usage") or {}
                counts = [usage.get("inputTokens"), usage.get("cacheReadTokens", 0),
                          usage.get("cacheWriteTokens", 0)]
                result.update(prompt_tokens=sum(counts) if all(type(n) is int for n in counts) else None,
                              prompt_cached_tokens=usage.get("cacheReadTokens"),
                              completion_tokens=usage.get("outputTokens"))
        elif provider == "codex":
            item = event.get("item") or {}
            if kind in ("item.started", "item.completed") and item.get("type") not in (
                    "agent_message", "reasoning"):
                used_tools = True
            if kind == "item.completed" and item.get("type") == "agent_message":
                messages.append(item.get("text") or "")
            if kind == "turn.completed":
                finished = True
                usage = event.get("usage") or {}
                result.update(done_reason=kind, prompt_tokens=usage.get("input_tokens"),
                              prompt_cached_tokens=usage.get("cached_input_tokens"),
                              completion_tokens=usage.get("output_tokens"),
                              reasoning_tokens=usage.get("reasoning_output_tokens"))
            if kind in ("turn.failed", "error"):
                failed = True
            if kind == "thread.started":
                result["session_id"] = event.get("thread_id")
        else:
            raise ValueError("Unknown CLI provider")
    if provider == "codex":
        result["raw"] = "\n".join(messages)
    for field in ("prompt_tokens", "prompt_cached_tokens", "completion_tokens", "reasoning_tokens"):
        if type(result[field]) is not int or result[field] < 0:
            result[field] = None
    if not isinstance(result["raw"], str):
        result["raw"], failed = "", True
    if used_tools:
        result["generation_error"] = "CLI attempted tool use; suite disqualified"
    elif failed or not finished or not result["raw"].strip():
        result["generation_error"] = "CLI failed or did not return a completed answer"
    return result


def command_for(config, executable, directory, model):
    if config["provider"] == "cursor":
        return ["powershell.exe", "-NoProfile", "-File", executable,
                "--workspace", directory, "--trust", "--model", model,
                "--mode", "ask", "--print", "--output-format", "stream-json"]
    return [executable, "exec", "--model", model, "--sandbox", "read-only",
            "--ephemeral", "--ignore-user-config", "--skip-git-repo-check", "--json",
            "--color", "never", "--cd", directory,
            "-c", 'model_reasoning_effort="' + config["reasoning_effort"] + '"',
            "-c", "project_doc_max_bytes=0", "-c", 'web_search="disabled"', "-"]


def generate_one(config, executable, model, prompt):
    """Only the final answer and public CLI metadata survive into benchmark records."""
    with tempfile.TemporaryDirectory(prefix="testgen-cli-") as directory:
        command = command_for(config, executable, directory, model)
        stdin = cli_prompt(prompt)
        if config["provider"] == "cursor":
            command.append(stdin)
            stdin = None
        events, lines = [], queue.Queue()
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=errors, text=True, encoding="utf-8", errors="replace",
                                       cwd=directory, creationflags=(subprocess.CREATE_NO_WINDOW
                                       if os.name == "nt" else 0))
            if stdin is not None:
                process.stdin.write(stdin)
            process.stdin.close()

            def read_lines():
                for line in process.stdout:
                    lines.put(line)
                lines.put(None)

            reader = threading.Thread(target=read_lines, daemon=True)
            reader.start()
            deadline = time.monotonic() + config["timeout_seconds"]
            interrupted = None
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        interrupted = "CLI timed out"
                        break
                    try:
                        line = lines.get(timeout=min(remaining, 1))
                    except queue.Empty:
                        continue
                    if line is None:
                        break
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    kind = event.get("type")
                    item_kind = (event.get("item") or {}).get("type")
                    if kind == "tool_call" or (kind in ("item.started", "item.completed")
                                               and item_kind not in ("agent_message", "reasoning")):
                        events.append({"type": "tool_call"} if config["provider"] == "cursor"
                                      else {"type": kind, "item": {"type": item_kind}})
                        interrupted = "CLI attempted tool use; process stopped"
                        break
                    # Do not retain reasoning summaries or echoed user/environment context.
                    if kind in ("system", "result", "turn.completed", "turn.failed", "error",
                                "thread.started") or (kind == "item.completed" and
                                                      item_kind == "agent_message"):
                        events.append(event)
            finally:
                if process.poll() is None:
                    if interrupted:
                        if os.name == "nt":
                            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                           capture_output=True, check=False)
                        else:
                            process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                reader.join(timeout=2)
                process.stdout.close()
            result = normalize_cli(config["provider"], events, process.returncode)
            result["exit_code"] = process.returncode
            if interrupted:
                result["generation_error"] = interrupted
            # Diagnostic errors are local CLI text, kept bounded; no credential files are read.
            errors.seek(0)
            diagnostic = errors.read(16000).decode("utf-8", errors="replace")
            failure_text = " ".join(str(e.get("message", e.get("error", ""))) for e in events
                                    if e.get("type") in ("error", "turn.failed"))
            if result.get("generation_error"):
                text = (diagnostic + " " + failure_text + " " + result["raw"]).lower()
                if any(word in text for word in ("usage limit", "rate limit", "quota", "resource_exhausted")):
                    result["blocked_reason"] = "subscription_limit"
                elif any(word in text for word in ("not supported", "not found", "invalid model", "unknown model",
                                                   "model_not_found", "model is not available", "access denied")):
                    result["blocked_reason"] = "model_unavailable"
                elif any(word in text for word in ("unauthorized", "not logged", "authentication", "login required")):
                    result["blocked_reason"] = "authentication"
                elif not result["raw"] and not interrupted:
                    result["blocked_reason"] = "cli_failure"
            return result
