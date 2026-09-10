from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = PROJECT_ROOT / "data" / "corpus.json"
DEFAULT_CASES = PROJECT_ROOT / "data" / "eval_cases.jsonl"
DEFAULT_THRESHOLDS = PROJECT_ROOT / "config" / "thresholds.json"
DEFAULT_JSON_REPORT = PROJECT_ROOT / "reports" / "latest.json"
DEFAULT_MARKDOWN_REPORT = PROJECT_ROOT / "reports" / "latest.md"

