"""Typed proposal contracts produced by Dosimeter workers."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from dosimeter.domain.dose import (
    LensDoseEquivalent,
    ShallowDoseEquivalent,
    TotalEffectiveDoseEquivalent,
)
from dosimeter.domain.rules import RuleResult


class NotificationClock(StrEnum):
    """Supported notification clocks from the notification worker."""

    IMMEDIATE = "immediate"
    TWENTY_FOUR_HOUR = "24_hour"
    NONE = "none"


class ReportingPath(StrEnum):
    """Written-report paths considered by the written-report worker."""

    SECTION_20_2203 = "20.2203"
    SECTION_20_2204 = "20.2204"
    NONE = "none"


class NotificationProposal(BaseModel):
    """
    Typed proposal from the Notification Worker.

    The worker proposes a notification result but does not transmit or
    persist a notification. Regulatory determinations must come from
    recorded deterministic rule results.
    """

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    notification_required: bool
    clock: NotificationClock

    tede: TotalEffectiveDoseEquivalent | None = None
    lens_dose: LensDoseEquivalent | None = None
    shallow_dose: ShallowDoseEquivalent | None = None

    rule_results: tuple[RuleResult, ...] = ()

    citations: tuple[str, ...] = ()

    explanation: str = Field(min_length=1)

    missing_fields: tuple[str, ...] = ()


class WrittenReportProposal(BaseModel):
    """
    Typed proposal from the Written Report Worker.

    The proposal records whether a written report is required and which
    regulatory reporting path applies. It never writes or transmits the
    report itself.
    """

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    report_required: bool
    reporting_path: ReportingPath

    tede: TotalEffectiveDoseEquivalent | None = None
    lens_dose: LensDoseEquivalent | None = None
    shallow_dose: ShallowDoseEquivalent | None = None

    rule_results: tuple[RuleResult, ...] = ()

    citations: tuple[str, ...] = ()

    explanation: str = Field(min_length=1)

    missing_fields: tuple[str, ...] = ()
