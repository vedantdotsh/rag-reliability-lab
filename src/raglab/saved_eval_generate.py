"""Generate one model response for each saved-evaluation JSONL case."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from raglab import testgen_api, testgen_cli
from raglab.general_eval import add_transport_arguments, transport_configuration
from raglab.saved_eval import _same_file, load_records

CLI_PREFIX = (
    "This is a prompt-only evaluation. Do not use tools, read or write files, run commands, "
    "browse, use MCP, or delegate. Return only the answer requested by the input.\n\n"
)


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def generate(
    records: list[dict],
    output: Path,
    model: str,
    *,
    api_config: dict | None = None,
    cli_config: dict | None = None,
    cli_executable: str | None = None,
) -> int:
    if bool(api_config) == bool(cli_config):
        raise ValueError("Choose exactly one API or CLI transport")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("A nonempty model ID is required")
    if cli_config and (
        not cli_executable
        or (shutil.which(cli_executable) is None and not Path(cli_executable).is_file())
    ):
        raise ValueError("--cli-executable must name an available executable")
    if any("generation" in record for record in records):
        raise ValueError("Input already contains generation provenance")
    key = testgen_api.api_key(api_config) if api_config else None
    adapter = Path(testgen_api.__file__) if api_config else Path(testgen_cli.__file__)
    run = {
        "source": "api" if api_config else "cli",
        "requested_model": model,
        "dataset_sha256": _digest(records),
        "adapter_sha256": hashlib.sha256(adapter.read_bytes()).hexdigest(),
        "configuration": api_config or cli_config,
        "total_cases": len(records),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    failures = 0
    with output.open("x", encoding="utf-8") as handle:
        for index, source in enumerate(records, 1):
            prompt = source["input"]
            generation = {
                **run,
                "case_index": index,
                "input_sha256": _digest(prompt),
                "requested_at": datetime.now(UTC).isoformat(),
            }
            started = time.perf_counter()
            try:
                if api_config:
                    public_request = testgen_api.request_for(api_config, model, prompt)
                    generation["request"] = public_request
                    result = testgen_api.generate_one(api_config, public_request, key)
                else:
                    generation["cli_prompt_sha256"] = _digest(CLI_PREFIX + prompt)
                    result = testgen_cli.generate_one(
                        cli_config, cli_executable, model, prompt, CLI_PREFIX
                    )
                generation.update(result)
                generation["request_sent"] = True
                generation["execution_status"] = (
                    "provider_error" if generation.get("generation_error") else "completed"
                )
            except (OSError, ValueError, KeyError) as error:
                generation.update(
                    raw="",
                    generation_error=str(error),
                    execution_status="harness_error",
                )
            generation["latency_seconds"] = round(time.perf_counter() - started, 3)
            response = generation.get("raw", "")
            if not isinstance(response, str):
                response = ""
                generation.update(
                    generation_error="Adapter returned a non-string response",
                    execution_status="provider_error",
                )
            failures += generation["execution_status"] != "completed"
            record = {**source, "response": response, "generation": generation}
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            handle.flush()
            detail = f" - {generation['generation_error']}" if generation.get(
                "generation_error"
            ) else ""
            print(f"{index}/{len(records)} {source['id']}{detail}", flush=True)
    return failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Saved-evaluation JSONL template")
    add_transport_arguments(parser)
    parser.add_argument("--cli-executable")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if _same_file(args.input, args.output):
            raise ValueError("output must not overwrite the input file")
        api_config, cli_config = transport_configuration(args)
        failures = generate(
            load_records(args.input),
            args.output,
            args.model,
            api_config=api_config,
            cli_config=cli_config,
            cli_executable=args.cli_executable,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"Generated {len(load_records(args.output))} cases in {args.output}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
