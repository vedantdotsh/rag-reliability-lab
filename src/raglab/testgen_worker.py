"""Run trusted benchmark code against generated JSON cases.

The parent supplies a timeout and isolated Python process. This is NOT a
sandbox for arbitrary code. Only author-written dataset Python is executed.
"""
import json
import math
import sys

MAX_PAYLOAD = 65536
ALLOWED_RAISES = {"ValueError", "TypeError", "KeyError", "IndexError", "ZeroDivisionError"}


def reject_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def check_value(value, depth=0):
    if depth > 8:
        raise ValueError("JSON nesting exceeds 8")
    kind = type(value)
    if value is None or kind is bool:
        return
    if kind in (int, float):
        if abs(value) > 1_000_000 or not math.isfinite(value):
            raise ValueError("Numbers must be finite and within +/-1000000")
    elif kind is str:
        if len(value) > 2000:
            raise ValueError("Strings must be at most 2000 characters")
    elif kind in (list, dict):
        if len(value) > 100:
            raise ValueError("Collections must contain at most 100 items")
        if kind is dict:
            if any(type(key) is not str or len(key) > 2000 for key in value):
                raise ValueError("Object keys must be bounded strings")
            value = value.values()
        for item in value:
            check_value(item, depth + 1)
    else:
        raise ValueError("Unsupported JSON value")


def validate_tests(tests):
    if type(tests) is not list or not 1 <= len(tests) <= 12:
        raise ValueError("Expected 1 to 12 test cases")
    for case in tests:
        if type(case) is not dict or set(case) not in (
            {"args", "expected"}, {"args", "raises"}
        ):
            raise ValueError("Each test needs args and exactly one of expected or raises")
        if type(case["args"]) is not list or len(case["args"]) > 6:
            raise ValueError("args must be a list of at most 6 values")
        check_value(case["args"])
        if "expected" in case:
            check_value(case["expected"])
        elif type(case["raises"]) is not str or case["raises"] not in ALLOWED_RAISES:
            raise ValueError("Unsupported exception name")
    return tests


def same_json(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(
            same_json(left[key], right[key]) for key in left
        )
    if type(left) is list:
        return len(left) == len(right) and all(map(same_json, left, right))
    return left == right


def execute(code, tests):
    outcomes = []
    for case in tests:
        namespace = {}
        try:
            exec(compile(code, "<trusted-dataset>", "exec"), namespace)  # noqa: S102 - trusted code only.
            target = namespace["target"]
        except Exception as error:  # noqa: BLE001 - dataset failures must be reported.
            return {"error": f"Dataset setup failed: {type(error).__name__}"}
        try:
            value = target(*case["args"])
        except Exception as error:  # noqa: BLE001 - exception type is the tested behavior.
            actual = {"raised": type(error).__name__}
            passed = case.get("raises") == type(error).__name__
        else:
            try:
                check_value(value)
            except ValueError as error:
                return {"error": f"Unsupported dataset return: {error}"}
            actual = {"returned": value}
            passed = "expected" in case and same_json(value, case["expected"])
        outcomes.append({"passed": passed, "actual": actual})
    return {"outcomes": outcomes}


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_PAYLOAD + 1)
        if len(raw) > MAX_PAYLOAD:
            raise ValueError("Payload exceeds 64 KiB")
        payload = json.loads(raw, parse_constant=reject_constant)
        if type(payload) is not dict or set(payload) != {"code", "tests"}:
            raise ValueError("Payload needs exactly code and tests")
        if type(payload["code"]) is not str or len(payload["code"]) > 16000:
            raise ValueError("Trusted code must be a string of at most 16000 characters")
        tests = validate_tests(payload["tests"])
        result = execute(payload["code"], tests)
    except (ValueError, UnicodeError, RecursionError) as error:
        result = {"error": str(error)}
    sys.stdout.buffer.write(json.dumps(result, allow_nan=False).encode("utf-8"))
    return 2 if "error" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
