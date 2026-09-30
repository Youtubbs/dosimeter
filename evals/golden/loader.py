"""Load and validate the machine-readable golden evaluation set."""

import json
from pathlib import Path

from evals.golden.models import GoldenCase


DEFAULT_GOLDEN_PATH = Path(__file__).with_name("cases.json")


def load_golden_cases(
    path: Path = DEFAULT_GOLDEN_PATH,
) -> tuple[GoldenCase, ...]:
    """Load and validate golden evaluation cases from JSON."""

    raw = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(raw, list):
        raise ValueError("Golden set must contain a JSON list of cases.")

    cases = tuple(GoldenCase.model_validate(item) for item in raw)

    case_ids = [case.case_id for case in cases]

    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Golden-set case IDs must be unique.")

    return cases
