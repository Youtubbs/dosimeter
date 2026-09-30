"""Golden evaluation runner."""

from dataclasses import dataclass, field

from dosimeter.config.settings import Settings
from dosimeter.harness.assess import run_assess
from dosimeter.repository import Session
from evals.golden.models import GoldenCase
from evals.golden.loader import load_golden_cases
from uuid import uuid4


@dataclass
class GoldenResult:
    """Result from evaluating one golden case."""

    case_id: str
    passed: bool
    expected_outcome: str
    actual_outcome: str | None = None
    failures: list[str] = field(default_factory=list)


def compare_outcome(
    case_id: str,
    expected: str,
    actual: str | None,
) -> GoldenResult:
    """Compare expected and actual workflow outcome."""

    failures: list[str] = []

    if expected != actual:
        failures.append(f"expected {expected}, got {actual}")

    return GoldenResult(
        case_id=case_id,
        passed=not failures,
        expected_outcome=expected,
        actual_outcome=actual,
        failures=failures,
    )


def run_exposure_case(
    session: Session,
    settings: Settings,
    case: GoldenCase,
    officer_code: str,
) -> GoldenResult:
    """Run a golden case backed by an exposure."""

    if case.exposure_id is None:
        raise ValueError(f"{case.id} does not contain an exposure_id")

    result = run_assess(
        session=session,
        exposure_id=case.exposure_id,
        officer_code=officer_code,
        settings=settings,
        session_id=uuid4(),
    )

    if result.partial is not None:
        print(f"{case.id} stopped early: {result.partial}")

    return compare_outcome(
        case.id,
        case.expected_outcome,
        result.outcome,
    )


def run_case(
    session: Session,
    settings: Settings,
    case: GoldenCase,
    officer_code: str,
) -> GoldenResult:
    """Execute a golden case using the correct evaluation path."""

    if case.exposure_id is not None:
        return run_exposure_case(
            session=session,
            settings=settings,
            case=case,
            officer_code=officer_code,
        )

    return GoldenResult(
        case_id=case.id,
        passed=False,
        expected_outcome=case.expected_outcome,
        failures=["No execution path implemented for this golden case."],
    )


def run_all_golden_cases(
    session: Session,
    settings: Settings,
    officer_code: str,
) -> list[GoldenResult]:
    """Run every golden case."""

    cases = load_golden_cases()

    return [
        run_case(
            session=session,
            settings=settings,
            case=case,
            officer_code=officer_code,
        )
        for case in cases
    ]
