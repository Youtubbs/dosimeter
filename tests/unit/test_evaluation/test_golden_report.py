from dosimeter.evaluation.golden import GoldenResult
from dosimeter.evaluation.golden_report import (
    build_report,
    format_report,
)


def test_build_report_counts_results():
    results = [
        GoldenResult(
            case_id="GOLD-001",
            passed=True,
            expected_outcome="required",
            actual_outcome="required",
        ),
        GoldenResult(
            case_id="GOLD-002",
            passed=False,
            expected_outcome="answer",
            actual_outcome="wrong",
            failures=["bad outcome"],
        ),
    ]

    report = build_report(results)

    assert report.total == 2
    assert report.passed == 1
    assert report.failed == 1


def test_format_report_contains_failure():
    report = build_report(
        [
            GoldenResult(
                case_id="GOLD-001",
                passed=False,
                expected_outcome="required",
                actual_outcome="wrong",
                failures=["bad outcome"],
            )
        ]
    )

    text = format_report(report)

    assert "GOLD-001" in text
    assert "bad outcome" in text
