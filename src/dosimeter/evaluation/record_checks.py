"""
The two evaluators that need no model at all: whether every threshold outcome
traces to a rules-engine invocation this turn, and whether any determination
rests on a source that is only proposed.

Both read the stored run record, so they assert facts rather than opinions.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dosimeter.repository import Session, queries

PROPOSED = "proposed"


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    passed: bool
    detail: str = ""
    offenders: list[str] = Field(default_factory=list)


def rules_engine_attribution(
    session: Session,
    run_id: UUID,
    claimed_rules: list[str],
) -> CheckResult:
    """Every rule a dossier names must have been invoked on this run."""

    detail = queries.run_record_detail(session, run_id)
    invoked = {row.rule_id for row in detail["rule_invocations"]}
    missing = sorted(set(claimed_rules) - invoked)

    return CheckResult(
        name="rules_engine_attribution",
        passed=not missing,
        detail=(
            "every claimed rule was invoked this turn"
            if not missing
            else "a threshold outcome has no rules-engine invocation this turn"
        ),
        offenders=missing,
    )


def source_status_accuracy(session: Session, run_id: UUID) -> CheckResult:
    """No determination may rest on a chunk whose status is proposed."""

    detail = queries.run_record_detail(session, run_id)

    offenders: list[str] = []
    for row in detail["retrievals"]:
        statuses = row.statuses or []
        chunk_ids = row.chunk_ids or []
        for chunk_id, status in zip(chunk_ids, statuses, strict=False):
            if status == PROPOSED and row.status_filter != PROPOSED:
                offenders.append(chunk_id)

    return CheckResult(
        name="source_status_accuracy",
        passed=not offenders,
        detail=(
            "no determination rests on a proposed source"
            if not offenders
            else "a determination retrieved a proposed source without asking for one"
        ),
        offenders=sorted(set(offenders)),
    )


def run_checks(session: Session, run_id: UUID, claimed_rules: list[str]) -> list[CheckResult]:
    return [
        rules_engine_attribution(session, run_id, claimed_rules),
        source_status_accuracy(session, run_id),
    ]
