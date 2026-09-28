"""Tests for worker graph-node adapters."""

from unittest.mock import Mock, patch

from dosimeter.config.settings import Bounds
from dosimeter.graph.workflow import Nodes, compile_graph
from dosimeter.domain.rules import RuleOutcome, RuleResult, RuleSource
from dosimeter.graph.state import DispatchPlan, Subject, initial_state, ReviewerVerdict
from dosimeter.tools.base import InvocationRecord
from dosimeter.workers.models import (
    NotificationClock,
    NotificationProposal,
    ReportingPath,
    WrittenReportProposal,
)
from dosimeter.workers.nodes import (
    make_notification_node,
    make_written_report_node,
)


SUBJECT = Subject(
    session_id="session-1",
    officer_id=1,
    officer_code="OFFICER-1",
    exposure_id="exposure-1",
)

SOURCE_R1 = RuleSource(
    citation="10 CFR 20.2202(a)",
    section="Immediate notification",
    status="in_force",
)

SOURCE_R3 = RuleSource(
    citation="10 CFR 20.2203",
    section="Reports of exposures and radiation levels",
    status="in_force",
)


def make_rule_result(
    rule_id: str,
    outcome: RuleOutcome,
    source: RuleSource,
) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        outcome=outcome,
        sources=(source,),
        inputs_used={},
        threshold={},
        explanation=f"{rule_id} test result.",
    )


def test_notification_node_adds_worker_proposal_to_graph_state() -> None:
    ledger = Mock()

    rule_result = make_rule_result(
        "R1",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R1,
    )

    proposal = NotificationProposal(
        notification_required=False,
        clock=NotificationClock.NONE,
        rule_results=(rule_result,),
        citations=("10 CFR 20.2202(a)",),
        explanation="Notification is not required.",
    )

    invocation = InvocationRecord(
        tool="evaluate_rule",
        arguments_sha256="hash-r1",
        arguments={"rule_id": "R1"},
        result={"rule_id": "R1"},
        outcome="ok",
        duration_ms=1.0,
    )

    state = initial_state(SUBJECT)
    state["dispatch_plan"] = DispatchPlan(
        workers=["notification"],
        goals={
            "notification": "Determine whether notification is required.",
        },
        rationale="Test notification dispatch.",
    )

    with patch(
        "dosimeter.workers.nodes.run_notification_worker",
        return_value=(proposal, [invocation]),
    ) as worker:
        node = make_notification_node(
            ledger=ledger,
            shared_tools=[],
        )

        result = node(state)

    assert "notification" in result["proposals"]

    graph_proposal = result["proposals"]["notification"]

    assert graph_proposal.worker == "notification"
    assert graph_proposal.kind == "notification"
    assert graph_proposal.payload["notification_required"] is False
    assert graph_proposal.payload["clock"] == "none"
    assert graph_proposal.citations == ["10 CFR 20.2202(a)"]

    assert len(result["rule_invocations"]) == 1
    assert result["rule_invocations"][0]["tool"] == "evaluate_rule"
    assert result["rule_invocations"][0]["outcome"] == "ok"

    worker.assert_called_once()

    call = worker.call_args.kwargs

    assert call["subject"].worker_id == "notification"
    assert call["subject"].exposure_id == SUBJECT.exposure_id
    assert call["ledger"] is ledger
    assert call["prompt"] == "Determine whether notification is required."


def test_written_report_node_adds_worker_proposal_to_graph_state() -> None:
    ledger = Mock()

    rule_result = make_rule_result(
        "R3",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R3,
    )

    proposal = WrittenReportProposal(
        report_required=False,
        reporting_path=ReportingPath.NONE,
        rule_results=(rule_result,),
        citations=("10 CFR 20.2203",),
        explanation="Written report is not required.",
    )

    invocation = InvocationRecord(
        tool="evaluate_rule",
        arguments_sha256="hash-r3",
        arguments={"rule_id": "R3"},
        result={"rule_id": "R3"},
        outcome="ok",
        duration_ms=1.0,
    )

    state = initial_state(SUBJECT)
    state["dispatch_plan"] = DispatchPlan(
        workers=["written_report"],
        goals={
            "written_report": "Determine whether a written report is required.",
        },
        rationale="Test written-report dispatch.",
    )

    with patch(
        "dosimeter.workers.nodes.run_written_report_worker",
        return_value=(proposal, [invocation]),
    ) as worker:
        node = make_written_report_node(
            ledger=ledger,
            shared_tools=[],
        )

        result = node(state)

    assert "written_report" in result["proposals"]

    graph_proposal = result["proposals"]["written_report"]

    assert graph_proposal.worker == "written_report"
    assert graph_proposal.kind == "written_report"
    assert graph_proposal.payload["report_required"] is False
    assert graph_proposal.payload["reporting_path"] == "none"
    assert graph_proposal.citations == ["10 CFR 20.2203"]

    assert len(result["rule_invocations"]) == 1
    assert result["rule_invocations"][0]["tool"] == "evaluate_rule"
    assert result["rule_invocations"][0]["outcome"] == "ok"

    worker.assert_called_once()

    call = worker.call_args.kwargs

    assert call["subject"].worker_id == "written_report"
    assert call["subject"].exposure_id == SUBJECT.exposure_id
    assert call["ledger"] is ledger
    assert call["prompt"] == "Determine whether a written report is required."


def test_notification_node_uses_default_prompt_without_dispatch_plan() -> None:
    ledger = Mock()

    proposal = NotificationProposal(
        notification_required=False,
        clock=NotificationClock.NONE,
        explanation="Notification is not required.",
    )

    state = initial_state(SUBJECT)

    with patch(
        "dosimeter.workers.nodes.run_notification_worker",
        return_value=(proposal, []),
    ) as worker:
        node = make_notification_node(
            ledger=ledger,
            shared_tools=[],
        )

        node(state)

    call = worker.call_args.kwargs

    assert call["prompt"] == ("Evaluate whether regulatory notification is required.")


def test_written_report_node_uses_default_prompt_without_dispatch_plan() -> None:
    ledger = Mock()

    proposal = WrittenReportProposal(
        report_required=False,
        reporting_path=ReportingPath.NONE,
        explanation="Written report is not required.",
    )

    state = initial_state(SUBJECT)

    with patch(
        "dosimeter.workers.nodes.run_written_report_worker",
        return_value=(proposal, []),
    ) as worker:
        node = make_written_report_node(
            ledger=ledger,
            shared_tools=[],
        )

        node(state)

    call = worker.call_args.kwargs

    assert call["prompt"] == ("Evaluate whether a regulatory written report is required.")


def test_real_worker_nodes_merge_parallel_proposals_in_graph() -> None:
    """Notification and written-report adapters merge into graph state."""

    ledger = Mock()

    notification_rule = make_rule_result(
        "R1",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R1,
    )

    written_report_rule = make_rule_result(
        "R3",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R3,
    )

    notification_proposal = NotificationProposal(
        notification_required=False,
        clock=NotificationClock.NONE,
        rule_results=(notification_rule,),
        citations=("10 CFR 20.2202(a)",),
        explanation="Notification is not required.",
    )

    written_report_proposal = WrittenReportProposal(
        report_required=False,
        reporting_path=ReportingPath.NONE,
        rule_results=(written_report_rule,),
        citations=("10 CFR 20.2203",),
        explanation="Written report is not required.",
    )

    notification_node = make_notification_node(
        ledger=ledger,
        shared_tools=[],
    )

    written_report_node = make_written_report_node(
        ledger=ledger,
        shared_tools=[],
    )

    def coordinator(state):
        del state

        return {
            "dispatch_plan": DispatchPlan(
                workers=[
                    "notification",
                    "written_report",
                ],
                goals={
                    "notification": "Evaluate notification requirements.",
                    "written_report": "Evaluate written-report requirements.",
                },
                rationale="Both regulatory workers are required.",
            )
        }

    def reviewer(state):
        assert "notification" in state["proposals"]
        assert "written_report" in state["proposals"]

        return {
            "reviewer_verdicts": [
                ReviewerVerdict(
                    iteration=1,
                    worker="notification",
                    verdict="approved",
                ),
                ReviewerVerdict(
                    iteration=1,
                    worker="written_report",
                    verdict="approved",
                ),
            ],
            "reviewer_iterations": 1,
        }

    def eligibility(state):
        del state

        return {
            "outcome": "ready_for_officer",
        }

    with (
        patch(
            "dosimeter.workers.nodes.run_notification_worker",
            return_value=(notification_proposal, []),
        ),
        patch(
            "dosimeter.workers.nodes.run_written_report_worker",
            return_value=(written_report_proposal, []),
        ),
    ):
        app = compile_graph(
            Nodes(
                coordinator=coordinator,
                notification=notification_node,
                written_report=written_report_node,
                reviewer=reviewer,
                eligibility_check=eligibility,
            ),
            Bounds(),
        )

        result = app.invoke(initial_state(SUBJECT))

    assert sorted(result["proposals"]) == [
        "notification",
        "written_report",
    ]

    notification = result["proposals"]["notification"]
    written_report = result["proposals"]["written_report"]

    assert notification.worker == "notification"
    assert notification.kind == "notification"
    assert notification.payload["notification_required"] is False

    assert written_report.worker == "written_report"
    assert written_report.kind == "written_report"
    assert written_report.payload["report_required"] is False

    assert result["outcome"] == "ready_for_officer"
