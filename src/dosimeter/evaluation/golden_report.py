"""Golden evaluation reporting."""

from dataclasses import dataclass

from dosimeter.evaluation.golden import GoldenResult


@dataclass
class GoldenReport:
    """Summary of a golden evaluation run."""

    total: int
    passed: int
    failed: int
    results: list[GoldenResult]


def build_report(
    results: list[GoldenResult],
) -> GoldenReport:
    """Create summary statistics from golden results."""

    passed = sum(
        1 for result in results if result.passed
    )

    failed = len(results) - passed

    return GoldenReport(
        total=len(results),
        passed=passed,
        failed=failed,
        results=results,
    )


def format_report(
    report: GoldenReport,
) -> str:
    """Render a human-readable report."""

    lines = [
        "Golden Evaluation Report",
        "========================",
        "",
        f"Total cases: {report.total}",
        f"Passed: {report.passed}",
        f"Failed: {report.failed}",
        "",
    ]

    failures = [
        result
        for result in report.results
        if not result.passed
    ]

    if failures:
        lines.append("Failures:")
        lines.append("")

        for result in failures:
            lines.append(result.case_id)

            for failure in result.failures:
                lines.append(
                    f"  - {failure}"
                )

    return "\n".join(lines)

