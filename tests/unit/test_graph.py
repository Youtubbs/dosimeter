"""Thread ids, state reducers and routing, all without a model or a database."""

from types import SimpleNamespace

import pytest
from langgraph.errors import GraphRecursionError

from dosimeter.config.settings import Bounds
from dosimeter.errors import BudgetError
from dosimeter.graph.graph import build_graph
from dosimeter.graph.nodes.coordinator import make_coordinator_node, route_after_coordinator
from dosimeter.graph.nodes.reviewer import make_reviewer_node, route_after_reviewer
from dosimeter.graph.schemas import DispatchPlan, ReviewerVerdict, Subject, WorkerProposal
from dosimeter.graph.state import add_usage, initial_state, merge_proposals
from dosimeter.graph.threads import THREAD_ID_FORMAT, Participant, thread_config, thread_id
from dosimeter.harness.budgets import REVIEWER_ITERATIONS, SessionLedger
from unittest.mock import Mock

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
    threads = {thread_id(7, "EXP-2026-0412", item) for item in Participant}

    assert len(threads) == len(Participant) == 5


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
    assert route_after_coordinator(state) == ["eligibility_check"]

    state["dispatch_plan"] = DispatchPlan(workers=[])
    assert route_after_coordinator(state) == ["eligibility_check"]


def test_a_rejection_goes_back_to_the_coordinator() -> None:
    state = initial_state(SUBJECT)
    state["reviewer_verdicts"] = [
        ReviewerVerdict(iteration=1, worker="written_report", verdict="rejected", reason="no cite")
    ]
    state["reviewer_iterations"] = 1

    assert route_after_reviewer(state, iteration_cap=3) == "coordinator"


def test_the_iteration_cap_ends_the_cycle_even_on_a_rejection() -> None:
    state = initial_state(SUBJECT)
    state["reviewer_verdicts"] = [
        ReviewerVerdict(iteration=3, worker="written_report", verdict="rejected")
    ]
    state["reviewer_iterations"] = 3

    assert route_after_reviewer(state, iteration_cap=3) == "eligibility_check"


def test_an_approval_falls_through_to_the_eligibility_check() -> None:
    state = initial_state(SUBJECT)
    state["reviewer_verdicts"] = [
        ReviewerVerdict(iteration=1, worker="notification", verdict="approved")
    ]

    assert route_after_reviewer(state, iteration_cap=3) == "eligibility_check"


def build_test_graph(monkeypatch: pytest.MonkeyPatch, dispatched: list[str]):
    """The real graph, with stand-in node bodies swapped in before it is built."""

    def coordinator(state):
        return {
            "dispatch_plan": DispatchPlan(
                workers=dispatched,
                rationale="test",
            )
        }

    def worker(name):
        def run(state, *, ledger=None, shared_tools=()):
            return {
                "proposals": {
                    name: WorkerProposal(
                        worker=name,
                        kind=name,
                    )
                },
                "usage": {"input_tokens": 10},
            }

        return run

    def reviewer(state):
        return {
            "reviewer_verdicts": [
                ReviewerVerdict(
                    iteration=1,
                    worker="notification",
                    verdict="approved",
                )
            ],
            "reviewer_iterations": state.get("reviewer_iterations", 0) + 1,
        }

    monkeypatch.setattr(
        "dosimeter.graph.graph.make_coordinator_node",
        lambda **_: coordinator,
    )

    monkeypatch.setattr(
        "dosimeter.graph.graph.notification_node",
        worker("notification"),
    )

    monkeypatch.setattr(
        "dosimeter.graph.graph.written_report_node",
        worker("written_report"),
    )

    monkeypatch.setattr(
        "dosimeter.graph.graph.build_equipment_node",
        lambda **_: worker("equipment"),
    )

    monkeypatch.setattr(
        "dosimeter.graph.graph.make_reviewer_node",
        lambda **_: reviewer,
    )

    return build_graph(
        Bounds(),
        ledger=Mock(),
        shared_tools=[],
    )


def test_two_parallel_legs_both_land_in_the_state(monkeypatch: pytest.MonkeyPatch) -> None:
    app = build_test_graph(monkeypatch, ["notification", "written_report"])

    result = app.invoke(initial_state(SUBJECT))

    assert sorted(result["proposals"]) == ["notification", "written_report"]
    assert result["usage"] == {"input_tokens": 20}
    assert result["outcome"] == "ready_for_officer"


def test_the_equipment_leg_only_runs_when_the_plan_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    result = build_test_graph(monkeypatch, ["notification"]).invoke(initial_state(SUBJECT))

    assert sorted(result["proposals"]) == ["notification"]


def test_a_turn_with_no_workers_still_reaches_the_end(monkeypatch: pytest.MonkeyPatch) -> None:
    result = build_test_graph(monkeypatch, []).invoke(initial_state(SUBJECT))

    assert result["proposals"] == {}
    assert result["outcome"] == "ready_for_officer"
    assert result["escalation"].reason() == "no trigger fired"


class FakeChatModel:
    """Stands in for get_chat_model(): with_structured_output(...).invoke(...), with token usage."""

    def __init__(self, plan: DispatchPlan, input_tokens: int, output_tokens: int) -> None:
        self.plan = plan
        self.usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}

    def with_structured_output(self, schema, include_raw=False):
        return self

    def invoke(self, messages):
        raw = SimpleNamespace(usage_metadata=self.usage)
        return {"raw": raw, "parsed": self.plan, "parsing_error": None}


class FakeRecorder:
    """Keeps what RunRecorder would have written for the Coordinator."""

    def __init__(self) -> None:
        self.dispatches: list[dict] = []
        self.model_calls: list[dict] = []

    def dispatched(self, worker, reason, iteration=1, redispatch_trigger=None) -> None:
        self.dispatches.append(
            {
                "worker": worker,
                "reason": reason,
                "iteration": iteration,
                "redispatch_trigger": redispatch_trigger,
            }
        )

    def model_called(self, **call) -> None:
        self.model_calls.append(call)


NARROWED_PLAN = DispatchPlan(
    workers=["written_report"],
    goals={"written_report": "check the 20.1206 conditions"},
    rationale="the first report was rejected",
)


def rejected_once() -> dict:
    state = initial_state(SUBJECT)
    state["reviewer_iterations"] = 1
    state["reviewer_verdicts"] = [
        ReviewerVerdict(
            iteration=1,
            worker="written_report",
            verdict="rejected",
            reason="unsupported by its cited text",
        )
    ]
    return state


def test_a_redispatch_is_recorded_with_the_rejection_that_caused_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "dosimeter.graph.nodes.coordinator.get_chat_model",
        lambda **_: FakeChatModel(NARROWED_PLAN, 200, 40),
    )
    ledger = SessionLedger(bounds=Bounds())
    recorder = FakeRecorder()

    make_coordinator_node(ledger=ledger, recorder=recorder)(rejected_once())

    assert recorder.dispatches == [
        {
            "worker": "written_report",
            "reason": "check the 20.1206 conditions",
            "iteration": 2,
            "redispatch_trigger": "written_report: unsupported by its cited text",
        }
    ]
    assert recorder.model_calls[0]["agent"] == "coordinator"
    assert ledger.session_tokens == 240


def test_the_coordinator_does_not_start_once_the_budget_is_spent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = Mock()
    monkeypatch.setattr("dosimeter.graph.nodes.coordinator.get_chat_model", lambda **_: model)
    ledger = SessionLedger(bounds=Bounds(max_session_tokens=100), session_input_tokens=100)

    with pytest.raises(BudgetError):
        make_coordinator_node(ledger=ledger)(initial_state(SUBJECT))

    model.with_structured_output.assert_not_called()


def always_rejecting_graph(monkeypatch: pytest.MonkeyPatch, bounds: Bounds):
    """Every review rejects, so only a cap can end the Reviewer loop."""

    def coordinator(state):
        return {"dispatch_plan": DispatchPlan(workers=["notification"], rationale="test")}

    def worker(state):
        return {"proposals": {"notification": WorkerProposal(worker="notification", kind="n")}}

    def reviewer(state):
        iteration = state.get("reviewer_iterations", 0) + 1
        return {
            "reviewer_verdicts": [
                ReviewerVerdict(iteration=iteration, worker="notification", verdict="rejected")
            ],
            "reviewer_iterations": iteration,
        }

    monkeypatch.setattr("dosimeter.graph.graph.make_coordinator_node", lambda **_: coordinator)
    monkeypatch.setattr("dosimeter.graph.graph.notification_node", worker)
    monkeypatch.setattr("dosimeter.graph.graph.make_reviewer_node", lambda **_: reviewer)

    return build_graph(bounds, ledger=Mock(), shared_tools=[])


def test_the_reviewer_loop_stops_at_its_iteration_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    app = always_rejecting_graph(monkeypatch, Bounds(reviewer_iteration_cap=3))

    result = app.invoke(initial_state(SUBJECT))

    assert result["reviewer_iterations"] == 3
    assert result["outcome"] is not None


def test_the_recursion_limit_stops_the_loop_even_when_the_cap_is_too_high(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = always_rejecting_graph(monkeypatch, Bounds(reviewer_iteration_cap=100))

    with pytest.raises(GraphRecursionError):
        app.invoke(initial_state(SUBJECT), {"recursion_limit": Bounds().max_recursion_depth})


def uncited_proposal_state() -> dict:
    """A proposal with no citations, so the Reviewer rejects without calling the judge."""

    state = initial_state(SUBJECT)
    state["proposals"] = {"notification": WorkerProposal(worker="notification", kind="n")}
    return state


def test_the_reviewer_records_each_iteration_against_the_ledger() -> None:
    ledger = SessionLedger(bounds=Bounds(reviewer_iteration_cap=3))

    make_reviewer_node(ledger=ledger)(uncited_proposal_state())

    assert ledger.turn.reviewer_iterations == 1


def test_the_reviewer_cap_on_the_ledger_is_reached_by_running_the_node() -> None:
    ledger = SessionLedger(bounds=Bounds(reviewer_iteration_cap=2))
    node = make_reviewer_node(ledger=ledger)
    state = uncited_proposal_state()

    state.update(node(state))
    assert ledger.check() is None

    state.update(node(state))

    assert ledger.turn.reviewer_iterations == 2
    assert ledger.check().ceiling == REVIEWER_ITERATIONS
