"""Run the golden evaluation suite."""

from dosimeter.config.settings import get_settings
from dosimeter.evaluation.golden import run_all_golden_cases
from dosimeter.evaluation.golden_report import (
    build_report,
    format_report,
)
from dosimeter.repository.connection import session_scope


DEFAULT_OFFICER = "OFF-101"


def main() -> None:
    """Execute golden evaluation and print report."""

    settings = get_settings()

    with session_scope() as session:
        results = run_all_golden_cases(
            session=session,
            settings=settings,
            officer_code=DEFAULT_OFFICER,
        )

    report = build_report(results)

    print(format_report(report))


if __name__ == "__main__":
    main()
