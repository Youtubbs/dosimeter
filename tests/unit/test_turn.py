"""A whole assess turn: rule inputs as the model sends them, the tool loop ending, workers that fail,
citations the Reviewer re-reads, re-dispatch, and the triggers read off the turn's own record."""

import json
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict

from dosimeter.config.settings import Bounds, NearBoundaryMargins
from dosimeter.graph.checkpointer import state_types
from dosimeter.graph.nodes.coordinator import route_after_coordinator
from dosimeter.graph.nodes.eligibility import (
    eligibility_node,
    route_on_readiness,
    signals_from_state,
)
from dosimeter.graph.nodes.reviewer import cited_source
from dosimeter.graph.schemas import DispatchPlan, ReviewerVerdict, Subject
from dosimeter.harness.budgets import SessionLedger
from dosimeter.models.bedrock import run_tool_loop
from dosimeter.tools.dispatcher import (
    InvocationRecord,
    Tool,
    ToolDispatcher,
    ToolErrorCode,
    build_registry,
)
from dosimeter.tools.proposals import PROPOSE_NOTIFICATION_TOOL
from dosimeter.tools.rules import EVALUATE_RULE_TOOL, evaluate_rule
from dosimeter.workers.models import NotificationProposal
from dosimeter.workers.nodes import make_notification_node

SUBJECT = Subject(session_id="s", officer_id=1, officer_code="OFF-101", exposure_id="EXP-2026-0412")

NOTIFICATION = {
    "notification_required": True,
    "clock": "immediate",
    "explanation": "Shallow dose of 310 rad meets the 250 rad threshold.",
    "citations": ["chunk-2202"],
}


class Nested(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int


class NestedInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal: Nested


def dispatcher(*tools: Tool) -> ToolDispatcher:
    return ToolDispatcher(
        registry=build_registry(list(tools)),
        ledger=SessionLedger(bounds=Bounds()),
        subject=SUBJECT,
    )


def rule_call(
    rule_id: str, outcome: str, inputs: dict | None = None, threshold: dict | None = None
) -> dict:
    return {
        "tool": "evaluate_rule",
        "result": {
            "rule_id": rule_id,
            "result": {
                "rule_id": rule_id,
                "outcome": outcome,
                "inputs_used": inputs or {},
                "threshold": threshold,
            },
        },
    }


def verdict(iteration: int, worker: str, decision: str) -> ReviewerVerdict:
    return ReviewerVerdict(iteration=iteration, worker=worker, verdict=decision, reason="")


def test_rule_inputs_arrive_as_json_strings_and_still_evaluate() -> None:
    r1 = evaluate_rule(
        {
            "rule_id": "R1",
            "inputs": {
                "tede": {"value": 4.1, "unit": "rem"},
                "lens": {"value": 9.0, "unit": "rem"},
                "shallow": {"value": 310, "unit": "rad", "site": "extremity"},
                "intake": {"value": 0.0},
            },
        }
    )
    r3 = evaluate_rule(
        {
            "rule_id": "R3",
            "inputs": {
                "r1_required": True,
                "r2_required": False,
                "population": "adult_worker",
                "annual_tede": {"value": 4.1, "unit": "rem"},
            },
        }
    )

    # the 310 rad shallow dose is the P2 trigger, so it must not be dropped for its string unit
    assert r1.result.outcome.value == "required"
    assert r3.result.outcome.value == "required"


def test_an_input_the_handler_rejects_goes_back_to_the_model_with_the_reason() -> None:
    response = dispatcher(EVALUATE_RULE_TOOL).invoke(
        "evaluate_rule", {"rule_id": "R1", "inputs": {"lens_dose": {"value": 9, "unit": "rem"}}}
    )

    assert response.error.reason_code == ToolErrorCode.INVALID_ARGUMENTS
    assert "lens_dose" in response.error.message


def test_a_nested_object_sent_as_a_json_string_is_decoded() -> None:
    tool = Tool(
        name="nested",
        description="takes a nested object",
        input_model=NestedInput,
        output_model=Nested,
        handler=lambda subject, arguments: arguments.proposal,
    )

    response = dispatcher(tool).invoke("nested", {"proposal": '{"value": 7}'})

    assert response.ok
    assert response.value == {"value": 7}


def test_a_proposal_without_citations_is_refused_inside_the_loop() -> None:
    response = dispatcher(PROPOSE_NOTIFICATION_TOOL).invoke(
        "propose_notification", {"proposal": {**NOTIFICATION, "citations": []}}
    )

    assert response.error.reason_code == ToolErrorCode.INVALID_ARGUMENTS
    assert "chunk_id" in response.error.message


class EndlessToolUse:
    """A model that would call propose_notification forever."""

    def __init__(self) -> None:
        self.calls = 0

    def converse(self, **_kwargs) -> dict:
        self.calls += 1
        return {
            "stopReason": "tool_use",
            "usage": {"inputTokens": 10, "outputTokens": 5},
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": f"t{self.calls}",
                                "name": "propose_notification",
                                "input": {"proposal": NOTIFICATION},
                            }
                        }
                    ],
                }
            },
        }


def test_the_tool_loop_ends_once_the_proposal_is_accepted() -> None:
    model = EndlessToolUse()

    with patch("dosimeter.models.bedrock.get_client", return_value=model):
        run_tool_loop(
            prompt="go",
            system_prompt="propose",
            tools=[PROPOSE_NOTIFICATION_TOOL],
            dispatcher=dispatcher(PROPOSE_NOTIFICATION_TOOL),
        )

    assert model.calls == 1


def test_a_worker_that_never_proposes_leaves_the_turn_running() -> None:
    with patch(
        "dosimeter.workers.nodes.run_notification_worker",
        side_effect=RuntimeError("loop exhausted"),
    ):
        node = make_notification_node(ledger=SessionLedger(bounds=Bounds()), shared_tools=[])

        assert node({"subject": SUBJECT}) == {}


def test_a_worker_logs_its_searches_so_the_reviewer_can_reread_them() -> None:
    search = {"query": "20.2202", "found": True, "sources": [{"chunk_id": "chunk-2202"}]}
    invocations = [
        InvocationRecord(
            tool="search_knowledge_base",
            arguments_sha256="a",
            arguments={},
            result=search,
            outcome="ok",
            duration_ms=1.0,
        )
    ]
    proposal = NotificationProposal.model_validate_json(json.dumps(NOTIFICATION))

    with patch(
        "dosimeter.workers.nodes.run_notification_worker", return_value=(proposal, invocations)
    ):
        node = make_notification_node(ledger=SessionLedger(bounds=Bounds()), shared_tools=[])
        update = node({"subject": SUBJECT})

    assert update["retrieval_log"] == [search]


def test_a_citation_resolves_by_chunk_id_or_by_the_section_it_quotes() -> None:
    log = [{"sources": [{"chunk_id": "chunk-2202", "section_path": "§ 20.2202"}]}]

    assert cited_source("chunk-2202", log)["chunk_id"] == "chunk-2202"
    assert cited_source("10 CFR 20.2202(a)", log)["chunk_id"] == "chunk-2202"
    assert cited_source("10 CFR 34.101(a)", log) is None


def test_an_approved_worker_is_not_dispatched_again() -> None:
    state = {
        "dispatch_plan": DispatchPlan(
            workers=["notification", "equipment"],
            goals={"notification": "again", "equipment": "again"},
            rationale="re-dispatch",
        ),
        "reviewer_verdicts": [
            verdict(1, "equipment", "approved"),
            verdict(1, "notification", "rejected"),
        ],
    }

    assert route_after_coordinator(state) == ["notification"]


def test_a_required_notification_rule_escalates_the_turn() -> None:
    state = {
        "reviewer_iterations": 1,
        "reviewer_verdicts": [verdict(1, "notification", "approved")],
        "rule_invocations": [rule_call("R1", "insufficient_data"), rule_call("R1", "required")],
    }

    update = eligibility_node(state)

    assert "notification_required" in update["escalation"].names()
    assert update["outcome"] == "escalated"


def test_approval_on_a_second_pass_is_not_approval_first_time() -> None:
    state = {
        "reviewer_iterations": 2,
        "reviewer_verdicts": [
            verdict(1, "notification", "rejected"),
            verdict(2, "notification", "approved"),
        ],
    }

    assert signals_from_state(state).reviewer_approved is False
    assert "reviewer_not_approved_first_time" in eligibility_node(state)["escalation"].names()


def test_a_dose_near_a_limit_and_a_dose_at_the_annual_limit_are_flagged() -> None:
    state = {
        "rule_invocations": [
            rule_call(
                "R1",
                "not_required",
                inputs={"shallow": {"value": 245, "unit": "rad"}},
                threshold={"shallow": {"value": 250.0, "unit": "rad"}},
            ),
            rule_call(
                "R3",
                "required",
                inputs={"annual_tede": {"value": 5.0, "unit": "rem"}},
                threshold={"tede": {"value": 5.0, "unit": "rem"}},
            ),
        ],
    }

    signals = signals_from_state(state, NearBoundaryMargins())

    assert signals.near_boundary_rules == ["R1 shallow", "R3 tede"]
    assert signals.doses_at_or_above_annual_limit == ["tede 5.0 rem"]


def test_a_low_confidence_dose_field_stops_the_turn_before_dispatch() -> None:
    assert route_on_readiness({"low_confidence_fields": []}) == "coordinator"
    assert (
        route_on_readiness({"low_confidence_fields": ["Total Effective Dose Equivalent"]})
        == "eligibility_check"
    )

    stopped = eligibility_node({"low_confidence_fields": ["Total Effective Dose Equivalent"]})

    assert stopped["escalation"].names() == ["field_below_confidence_floor"]


def test_every_type_in_graph_state_may_come_back_out_of_a_checkpoint() -> None:
    allowed = set(state_types())

    for needed in [
        ("dosimeter.graph.schemas", "Subject"),
        ("dosimeter.graph.schemas", "DispatchPlan"),
        ("dosimeter.domain.rules", "RuleResult"),
        ("dosimeter.rules.r3_written_report", "ExposurePopulation"),
        ("dosimeter.workers.models", "ReportingPath"),
    ]:
        assert needed in allowed


def test_a_dose_the_packet_gave_no_number_for_stops_the_turn_and_is_named() -> None:
    state = {"missing_dose_fields": ["Lens Dose Equivalent"]}

    assert route_on_readiness(state) == "eligibility_check"
    assert signals_from_state(state).fields_below_floor == ["Lens Dose Equivalent (not readable)"]
