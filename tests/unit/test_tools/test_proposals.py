"""Tests for worker proposal tools."""

import pytest
from pydantic import ValidationError

from dosimeter.domain.dose import (
    DoseUnit,
    TotalEffectiveDoseEquivalent,
)
from dosimeter.tools.proposals import (
    propose_notification,
    propose_written_report,
)
from dosimeter.workers.models import (
    NotificationClock,
    NotificationProposal,
    ReportingPath,
    WrittenReportProposal,
)


def make_tede(value: float) -> TotalEffectiveDoseEquivalent:
    """Create a TEDE quantity for proposal tests."""

    return TotalEffectiveDoseEquivalent(
        value=value,
        unit=DoseUnit.REM,
    )


# ---------------------------------------------------------------------------
# Notification proposal
# ---------------------------------------------------------------------------


def test_propose_notification_returns_typed_proposal() -> None:
    proposal = NotificationProposal(
        notification_required=True,
        clock=NotificationClock.IMMEDIATE,
        tede=make_tede(25.0),
        citations=("10 CFR 20.2202",),
        explanation="Immediate notification is required.",
    )

    result = propose_notification(proposal)

    assert isinstance(result, NotificationProposal)
    assert result.notification_required is True
    assert result.clock == NotificationClock.IMMEDIATE
    assert result.tede == make_tede(25.0)


def test_propose_notification_accepts_valid_mapping() -> None:
    proposal = {
        "notification_required": False,
        "clock": NotificationClock.NONE,
        "citations": ("10 CFR 20.2202",),
        "explanation": "No notification tier was triggered.",
    }

    result = propose_notification(proposal)

    assert isinstance(result, NotificationProposal)
    assert result.notification_required is False
    assert result.clock == NotificationClock.NONE


def test_propose_notification_rejects_missing_explanation() -> None:
    proposal = {
        "notification_required": True,
        "clock": NotificationClock.IMMEDIATE,
    }

    with pytest.raises(ValidationError):
        propose_notification(proposal)


def test_propose_notification_rejects_unknown_field() -> None:
    proposal = {
        "notification_required": False,
        "clock": NotificationClock.NONE,
        "explanation": "No notification required.",
        "made_up_field": "not allowed",
    }

    with pytest.raises(ValidationError):
        propose_notification(proposal)


# ---------------------------------------------------------------------------
# Written report proposal
# ---------------------------------------------------------------------------


def test_propose_written_report_returns_typed_proposal() -> None:
    proposal = WrittenReportProposal(
        report_required=True,
        reporting_path=ReportingPath.SECTION_20_2203,
        tede=make_tede(6.0),
        citations=("10 CFR 20.2203",),
        explanation="A written report is required.",
    )

    result = propose_written_report(proposal)

    assert isinstance(result, WrittenReportProposal)
    assert result.report_required is True
    assert result.reporting_path == ReportingPath.SECTION_20_2203
    assert result.tede == make_tede(6.0)


def test_propose_written_report_accepts_valid_mapping() -> None:
    proposal = {
        "report_required": True,
        "reporting_path": ReportingPath.SECTION_20_2204,
        "citations": (
            "10 CFR 20.1206",
            "10 CFR 20.2204",
        ),
        "explanation": ("The planned-special-exposure reporting path applies."),
    }

    result = propose_written_report(proposal)

    assert isinstance(result, WrittenReportProposal)
    assert result.report_required is True
    assert result.reporting_path == ReportingPath.SECTION_20_2204


def test_propose_written_report_rejects_missing_path() -> None:
    proposal = {
        "report_required": True,
        "explanation": "A written report is required.",
    }

    with pytest.raises(ValidationError):
        propose_written_report(proposal)


def test_propose_written_report_rejects_unknown_field() -> None:
    proposal = {
        "report_required": False,
        "reporting_path": ReportingPath.NONE,
        "explanation": "No written report is required.",
        "unexpected": True,
    }

    with pytest.raises(ValidationError):
        propose_written_report(proposal)
