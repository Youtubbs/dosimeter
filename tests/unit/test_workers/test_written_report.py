"""Tests for the Written Report Worker."""

from unittest.mock import Mock, patch

import pytest
from pydantic import BaseModel, ConfigDict

from dosimeter.domain.rules import (
    RuleOutcome,
    RuleResult,
    RuleSource,
)
from dosimeter.graph.state import Subject
from dosimeter.tools.base import InvocationRecord, Tool
from dosimeter.workers.models import ReportingPath
from dosimeter.workers.written_report import (
    build_written_report_proposal,
    run_written_report_worker,
)


SOURCE_R3 = RuleSource(
    citation="10 CFR 20.2203",
    section="Reports of exposures and radiation levels",
    status="in_force",
)

SOURCE_R4 = RuleSource(
    citation="10 CFR 20.1206",
    section="Planned special exposures",
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
    """Create a harmless shared tool for worker-runtime tests."""

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


def test_r3_required_proposes_section_20_2203_report() -> None:
    r3 = make_result(
        "R3",
        RuleOutcome.REQUIRED,
        SOURCE_R3,
    )

    r4 = make_result(
        "R4",
        RuleOutcome.INVALID,
        SOURCE_R4,
    )

    result = build_written_report_proposal(
        r3_result=r3,
        r4_result=r4,
    )

    assert result.report_required is True
    assert result.reporting_path == ReportingPath.SECTION_20_2203


def test_valid_pse_uses_section_20_2204_path() -> None:
    r3 = make_result(
        "R3",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R3,
    )

    r4 = make_result(
        "R4",
        RuleOutcome.VALID,
        SOURCE_R4,
    )

    result = build_written_report_proposal(
        r3_result=r3,
        r4_result=r4,
    )

    assert result.report_required is True
    assert result.reporting_path == ReportingPath.SECTION_20_2204


def test_valid_pse_path_takes_priority_over_r3() -> None:
    r3 = make_result(
        "R3",
        RuleOutcome.REQUIRED,
        SOURCE_R3,
    )

    r4 = make_result(
        "R4",
        RuleOutcome.VALID,
        SOURCE_R4,
    )

    result = build_written_report_proposal(
        r3_result=r3,
        r4_result=r4,
    )

    assert result.report_required is True
    assert result.reporting_path == ReportingPath.SECTION_20_2204


def test_no_report_when_neither_path_applies() -> None:
    r3 = make_result(
        "R3",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R3,
    )

    r4 = make_result(
        "R4",
        RuleOutcome.INVALID,
        SOURCE_R4,
    )

    result = build_written_report_proposal(
        r3_result=r3,
        r4_result=r4,
    )

    assert result.report_required is False
    assert result.reporting_path == ReportingPath.NONE


def test_insufficient_r3_data_is_preserved() -> None:
    r3 = make_result(
        "R3",
        RuleOutcome.INSUFFICIENT_DATA,
        SOURCE_R3,
        missing_fields=("annual_tede",),
    )

    r4 = make_result(
        "R4",
        RuleOutcome.INVALID,
        SOURCE_R4,
    )

    result = build_written_report_proposal(
        r3_result=r3,
        r4_result=r4,
    )

    assert result.report_required is False
    assert result.reporting_path == ReportingPath.NONE
    assert "annual_tede" in result.missing_fields


def test_insufficient_r4_data_is_preserved() -> None:
    r3 = make_result(
        "R3",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R3,
    )

    r4 = make_result(
        "R4",
        RuleOutcome.INSUFFICIENT_DATA,
        SOURCE_R4,
        missing_fields=("written_authorization",),
    )

    result = build_written_report_proposal(
        r3_result=r3,
        r4_result=r4,
    )

    assert result.report_required is False
    assert result.reporting_path == ReportingPath.NONE
    assert "written_authorization" in result.missing_fields


def test_written_report_proposal_contains_rule_results() -> None:
    r3 = make_result(
        "R3",
        RuleOutcome.REQUIRED,
        SOURCE_R3,
    )

    r4 = make_result(
        "R4",
        RuleOutcome.INVALID,
        SOURCE_R4,
    )

    result = build_written_report_proposal(
        r3_result=r3,
        r4_result=r4,
    )

    assert result.rule_results == (r3, r4)


def test_written_report_proposal_preserves_citations() -> None:
    r3 = make_result(
        "R3",
        RuleOutcome.REQUIRED,
        SOURCE_R3,
    )

    r4 = make_result(
        "R4",
        RuleOutcome.INVALID,
        SOURCE_R4,
    )

    result = build_written_report_proposal(
        r3_result=r3,
        r4_result=r4,
    )

    assert "10 CFR 20.2203" in result.citations
    assert "10 CFR 20.1206" in result.citations


def test_run_written_report_worker_uses_written_report_toolset() -> None:
    subject = Subject(
        session_id="session-1",
        officer_id=1,
        officer_code="OFFICER-1",
        exposure_id="exposure-1",
        worker_id="written_report",
    )

    ledger = Mock()

    shared_tools = [
        _shared_tool("get_exposure_extraction"),
        _shared_tool("search_knowledge_base"),
    ]

    r3 = make_result(
        "R3",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R3,
    )

    r4 = make_result(
        "R4",
        RuleOutcome.INVALID,
        SOURCE_R4,
    )

    # InvocationRecord stores Python-mode values. This is intentional:
    # WrittenReportProposal is strict and expects actual enum/tuple types
    # when reconstructed internally.
    proposal_data = {
        "report_required": False,
        "reporting_path": ReportingPath.NONE,
        "tede": None,
        "lens_dose": None,
        "shallow_dose": None,
        "rule_results": (r3, r4),
        "citations": (
            "10 CFR 20.2203",
            "10 CFR 20.1206",
        ),
        "explanation": "No written-report criteria were satisfied.",
        "missing_fields": (),
    }

    def fake_tool_loop(**kwargs):
        dispatcher = kwargs["dispatcher"]

        dispatcher.invocations.append(
            InvocationRecord(
                tool="propose_written_report",
                arguments_sha256="test-hash",
                arguments=proposal_data,
                result=proposal_data,
                outcome="ok",
                duration_ms=1.0,
            )
        )

        return "Written-report evaluation complete."

    with patch(
        "dosimeter.workers.written_report.run_tool_loop",
        side_effect=fake_tool_loop,
    ) as tool_loop:
        proposal, invocations = run_written_report_worker(
            subject=subject,
            ledger=ledger,
            shared_tools=shared_tools,
            prompt="Evaluate the current exposure.",
        )

    assert proposal.report_required is False
    assert proposal.reporting_path == ReportingPath.NONE
    assert proposal.explanation == "No written-report criteria were satisfied."

    assert proposal.rule_results == (r3, r4)

    assert len(invocations) == 1
    assert invocations[0].tool == "propose_written_report"
    assert invocations[0].outcome == "ok"

    tool_loop.assert_called_once()

    call = tool_loop.call_args.kwargs

    assert call["prompt"] == "Evaluate the current exposure."
    assert call["dispatcher"].subject == subject
    assert call["dispatcher"].ledger is ledger

    assert sorted(tool.name for tool in call["tools"]) == [
        "evaluate_rule",
        "get_exposure_extraction",
        "propose_written_report",
        "search_knowledge_base",
    ]


def test_run_written_report_worker_rejects_missing_proposal() -> None:
    subject = Subject(
        session_id="session-1",
        officer_id=1,
        officer_code="OFFICER-1",
        exposure_id="exposure-1",
        worker_id="written_report",
    )

    ledger = Mock()

    shared_tools = [
        _shared_tool("get_exposure_extraction"),
        _shared_tool("search_knowledge_base"),
    ]

    with (
        patch(
            "dosimeter.workers.written_report.run_tool_loop",
            return_value="I finished without proposing anything.",
        ),
        pytest.raises(
            RuntimeError,
            match="finished without producing",
        ),
    ):
        run_written_report_worker(
            subject=subject,
            ledger=ledger,
            shared_tools=shared_tools,
            prompt="Evaluate the current exposure.",
        )
