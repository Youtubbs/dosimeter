"""Thread ids, state reducers and routing, all without a model or a database."""

from __future__ import annotations

import pytest

from dosimeter.config.settings import Bounds
from dosimeter.graph.state import (
    DispatchPlan,
    ReviewerVerdict,
    Subject,
    WorkerProposal,
    add_usage,
    initial_state,
    merge_proposals,
)
from dosimeter.graph.threads import (
    THREAD_ID_FORMAT,
    Participant,
    thread_config,
    thread_id,
    thread_ids,
)
from dosimeter.graph.workflow import (
    COORDINATOR,
    ELIGIBILITY,
    Nodes,
    compile_graph,
    route_after_coordinator,
    route_after_reviewer,
)

SUBJECT = Subject(
    session_id="session-1",
    officer_id=7,
    officer_code="OFF-101",
    exposure_id="EXP-2026-0412",
)


def test_a_thread_id_is_the_same_string_every_time() -> None:
    first = thread_id(7, "EXP-2026-0412", Participant.REVIEWER)
    second = thread_id(7, "EXP-2026-0412", "reviewer")

    assert first == second == "dosimeter:v1:7:EXP-2026-0412:reviewer"
    assert THREAD_ID_FORMAT.count("{") == 3


def test_every_participant_gets_its_own_thread() -> None:
    threads = thread_ids(7, "EXP-2026-0412")

    assert len(set(threads.values())) == len(threads) == 5
    assert threads["reviewer"] != threads["written_report"]


def test_a_different_officer_or_exposure_is_a_different_thread() -> None:
    base = thread_id(7, "EXP-2026-0412", Participant.COORDINATOR)

    assert thread_id(8, "EXP-2026-0412", Participant.COORDINATOR) != base
    assert thread_id(7, "EXP-2026-0411", Participant.COORDINATOR) != base


def test_an_unknown_participant_is_refused() -> None:
    with pytest.raises(ValueError):
        thread_id(7, "EXP-2026-0412", "auditor")


def test_the_run_config_carries_the_thread_and_the_recursion_limit() -> None:
    config = thread_config(7, "EXP-2026-0412", Participant.NOTIFICATION, recursion_limit=12)

    assert config["configurable"]["thread_id"].endswith(":notification")
    assert config["recursion_limit"] == 12


def test_parallel_proposals_merge_without_clobbering() -> None:
    left = {"notification": WorkerProposal(worker="notification", kind="notification")}
    right = {"written_report": WorkerProposal(worker="written_report", kind="report")}

    merged = merge_proposals(left, right)

    assert sorted(merged) == ["notification", "written_report"]


def test_usage_adds_up() -> None:
    assert add_usage({"input_tokens": 10}, {"input_tokens": 5, "output_tokens": 2}) == {
        "input_tokens": 15,
        "output_tokens": 2,
    }


def test_a_dispatch_plan_rejects_a_worker_that_does_not_exist() -> None:
    with pytest.raises(ValueError):
        DispatchPlan(workers=["notification", "auditor"]).validated_workers()


def test_routing_follows_the_plan_rather_than_dispatching_everything() -> None:
    state = initial_state(SUBJECT)
    state["dispatch_plan"] = DispatchPlan(workers=["notification", "written_report"])

    assert route_after_coordinator(state) == ["notification", "written_report"]


def test_no_plan_and_an_empty_plan_both_skip_the_workers() -> None:
    state = initial_state(SUBJECT)
    assert route_after_coordinator(state) == [ELIGIBILITY]

    state["dispatch_plan"] = DispatchPlan(workers=[])
    assert route_after_coordinator(state) == [ELIGIBILITY]


def test_a_rejection_goes_back_to_the_coordinator() -> None:
    state = initial_state(SUBJECT)
    state["reviewer_verdicts"] = [
        ReviewerVerdict(iteration=1, worker="written_report", verdict="rejected", reason="no cite")
    ]
    state["reviewer_iterations"] = 1

    assert route_after_reviewer(state, Bounds()) == COORDINATOR


def test_the_iteration_cap_ends_the_cycle_even_on_a_rejection() -> None:
    state = initial_state(SUBJECT)
    state["reviewer_verdicts"] = [
        ReviewerVerdict(iteration=3, worker="written_report", verdict="rejected")
    ]
    state["reviewer_iterations"] = 3

    assert route_after_reviewer(state, Bounds(reviewer_iteration_cap=3)) == ELIGIBILITY


def test_an_approval_falls_through_to_the_eligibility_check() -> None:
    state = initial_state(SUBJECT)
    state["reviewer_verdicts"] = [
        ReviewerVerdict(iteration=1, worker="notification", verdict="approved")
    ]

    assert route_after_reviewer(state, Bounds()) == ELIGIBILITY


def build_test_graph(dispatched: list[str]):
    def coordinator(state):
        return {"dispatch_plan": DispatchPlan(workers=dispatched, rationale="test")}

    def worker(name):
        def run(state):
            return {
                "proposals": {name: WorkerProposal(worker=name, kind=name)},
                "usage": {"input_tokens": 10},
            }

        return run

    def reviewer(state):
        return {
            "reviewer_verdicts": [
                ReviewerVerdict(iteration=1, worker="notification", verdict="approved")
            ],
            "reviewer_iterations": state.get("reviewer_iterations", 0) + 1,
        }

    def eligibility(state):
        return {"outcome": "ready_for_officer"}

    return compile_graph(
        Nodes(
            coordinator=coordinator,
            notification=worker("notification"),
            written_report=worker("written_report"),
            equipment=worker("equipment"),
            reviewer=reviewer,
            eligibility_check=eligibility,
        ),
        Bounds(),
    )


def test_two_parallel_legs_both_land_in_the_state() -> None:
    app = build_test_graph(["notification", "written_report"])

    result = app.invoke(initial_state(SUBJECT))

    assert sorted(result["proposals"]) == ["notification", "written_report"]
    assert result["usage"] == {"input_tokens": 20}
    assert result["outcome"] == "ready_for_officer"


def test_the_equipment_leg_only_runs_when_the_plan_says_so() -> None:
    result = build_test_graph(["notification"]).invoke(initial_state(SUBJECT))

    assert sorted(result["proposals"]) == ["notification"]


def test_a_turn_with_no_workers_still_reaches_the_end() -> None:
    result = build_test_graph([]).invoke(initial_state(SUBJECT))

    assert result["proposals"] == {}
    assert result["outcome"] == "ready_for_officer"
