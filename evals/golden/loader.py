"""Load and validate the machine-readable golden evaluation set."""

import json
from pathlib import Path

from evals.golden.models import GoldenCase


DEFAULT_GOLDEN_DIR = Path(__file__).parent


def load_golden_cases(
    directory: Path = DEFAULT_GOLDEN_DIR,
) -> tuple[GoldenCase, ...]:
    """Load and validate every individual golden-case JSON file."""

    paths = sorted(path for path in directory.glob("*.json") if path.name != "cases.json")

    cases = tuple(
        GoldenCase.model_validate(json.loads(path.read_text(encoding="utf-8"))) for path in paths
    )

    case_ids = [case.id for case in cases]

    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Golden-set case IDs must be unique.")

    return cases
