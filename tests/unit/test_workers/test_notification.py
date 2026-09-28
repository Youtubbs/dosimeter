"""Tests for the Notification Worker."""

from unittest.mock import Mock, patch

import pytest
from pydantic import BaseModel, ConfigDict

from dosimeter.domain.rules import RuleOutcome, RuleResult, RuleSource
from dosimeter.graph.state import Subject
from dosimeter.tools.base import InvocationRecord, Tool
from dosimeter.workers.models import (
    NotificationClock,
    NotificationProposal,
)
from dosimeter.workers.notification import (
    build_notification_proposal,
    run_notification_worker,
)


SOURCE_R1 = RuleSource(
    citation="10 CFR 20.2202(a)",
    section="Immediate notification",
    status="in_force",
)

SOURCE_R2 = RuleSource(
    citation="10 CFR 20.2202(b)",
    section="Twenty-four hour notification",
    status="in_force",
)


class WorkerTestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkerTestOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True


def _worker_test_handler(
    subject: Subject,
    arguments: BaseModel,
) -> BaseModel:
    del subject
    del arguments
    return WorkerTestOutput()


def _shared_tool(name: str) -> Tool:
    return Tool(
        name=name,
        description=f"Test tool: {name}",
        input_model=WorkerTestInput,
        output_model=WorkerTestOutput,
        handler=_worker_test_handler,
    )


def make_result(
    rule_id: str,
    outcome: RuleOutcome,
    source: RuleSource,
    *,
    missing_fields: tuple[str, ...] = (),
) -> RuleResult:
    """Create a deterministic rule result for worker tests."""

    return RuleResult(
        rule_id=rule_id,
        outcome=outcome,
        sources=(source,),
        inputs_used={},
        threshold={},
        explanation=f"{rule_id} test result.",
        missing_fields=missing_fields,
    )


def test_r1_required_proposes_immediate_notification() -> None:
    r1 = make_result(
        "R1",
        RuleOutcome.REQUIRED,
        SOURCE_R1,
    )

    r2 = make_result(
        "R2",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R2,
    )

    result = build_notification_proposal(
        r1_result=r1,
        r2_result=r2,
    )

    assert result.notification_required is True
    assert result.clock == NotificationClock.IMMEDIATE


def test_r2_required_proposes_twenty_four_hour_notification() -> None:
    r1 = make_result(
        "R1",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R1,
    )

    r2 = make_result(
        "R2",
        RuleOutcome.REQUIRED,
        SOURCE_R2,
    )

    result = build_notification_proposal(
        r1_result=r1,
        r2_result=r2,
    )

    assert result.notification_required is True
    assert result.clock == NotificationClock.TWENTY_FOUR_HOUR


def test_r1_takes_priority_when_both_rules_require_notification() -> None:
    r1 = make_result(
        "R1",
        RuleOutcome.REQUIRED,
        SOURCE_R1,
    )

    r2 = make_result(
        "R2",
        RuleOutcome.REQUIRED,
        SOURCE_R2,
    )

    result = build_notification_proposal(
        r1_result=r1,
        r2_result=r2,
    )

    assert result.notification_required is True
    assert result.clock == NotificationClock.IMMEDIATE


def test_no_notification_when_neither_rule_fires() -> None:
    r1 = make_result(
        "R1",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R1,
    )

    r2 = make_result(
        "R2",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R2,
    )

    result = build_notification_proposal(
        r1_result=r1,
        r2_result=r2,
    )

    assert result.notification_required is False
    assert result.clock == NotificationClock.NONE


def test_insufficient_data_is_preserved() -> None:
    r1 = make_result(
        "R1",
        RuleOutcome.INSUFFICIENT_DATA,
        SOURCE_R1,
        missing_fields=("annual_tede",),
    )

    r2 = make_result(
        "R2",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R2,
    )

    result = build_notification_proposal(
        r1_result=r1,
        r2_result=r2,
    )

    assert result.notification_required is False
    assert result.clock == NotificationClock.NONE
    assert "annual_tede" in result.missing_fields


def test_notification_proposal_contains_rule_results() -> None:
    r1 = make_result(
        "R1",
        RuleOutcome.REQUIRED,
        SOURCE_R1,
    )

    r2 = make_result(
        "R2",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R2,
    )

    result = build_notification_proposal(
        r1_result=r1,
        r2_result=r2,
    )

    assert result.rule_results == (r1, r2)


def test_notification_proposal_preserves_citations() -> None:
    r1 = make_result(
        "R1",
        RuleOutcome.REQUIRED,
        SOURCE_R1,
    )

    r2 = make_result(
        "R2",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R2,
    )

    result = build_notification_proposal(
        r1_result=r1,
        r2_result=r2,
    )

    assert "10 CFR 20.2202(a)" in result.citations
    assert "10 CFR 20.2202(b)" in result.citations


def test_run_notification_worker_uses_notification_toolset() -> None:
    subject = Subject(
        session_id="session-1",
        officer_id=1,
        officer_code="OFFICER-1",
        exposure_id="exposure-1",
        worker_id="notification",
    )

    ledger = Mock()

    shared_tools = [
        _shared_tool("get_exposure_extraction"),
        _shared_tool("search_knowledge_base"),
    ]

    r1 = make_result(
        "R1",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R1,
    )

    r2 = make_result(
        "R2",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R2,
    )

    expected_proposal = NotificationProposal(
        notification_required=False,
        clock=NotificationClock.NONE,
        rule_results=(r1, r2),
        citations=(
            "10 CFR 20.2202(a)",
            "10 CFR 20.2202(b)",
        ),
        explanation="No notification criteria were satisfied.",
        missing_fields=(),
    )

    proposal_data = expected_proposal.model_dump()

    def fake_tool_loop(**kwargs):
        dispatcher = kwargs["dispatcher"]

        dispatcher.invocations.append(
            InvocationRecord(
                tool="propose_notification",
                arguments_sha256="test-hash",
                arguments=proposal_data,
                result=proposal_data,
                outcome="ok",
                duration_ms=1.0,
            )
        )

        return "Notification evaluation complete."

    with patch(
        "dosimeter.workers.notification.run_tool_loop",
        side_effect=fake_tool_loop,
    ) as tool_loop:
        proposal, invocations = run_notification_worker(
            subject=subject,
            ledger=ledger,
            shared_tools=shared_tools,
            prompt="Evaluate the current exposure.",
        )

    assert proposal == expected_proposal

    assert len(invocations) == 1
    assert invocations[0].tool == "propose_notification"

    tool_loop.assert_called_once()

    call = tool_loop.call_args.kwargs

    assert call["prompt"] == "Evaluate the current exposure."
    assert call["dispatcher"].subject == subject
    assert call["dispatcher"].ledger is ledger

    assert sorted(tool.name for tool in call["tools"]) == [
        "evaluate_rule",
        "get_exposure_extraction",
        "propose_notification",
        "search_knowledge_base",
    ]


def test_run_notification_worker_rejects_missing_proposal() -> None:
    subject = Subject(
        session_id="session-1",
        officer_id=1,
        officer_code="OFFICER-1",
        exposure_id="exposure-1",
        worker_id="notification",
    )

    ledger = Mock()

    shared_tools = [
        _shared_tool("get_exposure_extraction"),
        _shared_tool("search_knowledge_base"),
    ]

    with (
        patch(
            "dosimeter.workers.notification.run_tool_loop",
            return_value="I finished without proposing anything.",
        ),
        pytest.raises(
            RuntimeError,
            match="finished without producing",
        ),
    ):
        run_notification_worker(
            subject=subject,
            ledger=ledger,
            shared_tools=shared_tools,
            prompt="Evaluate the current exposure.",
        )
