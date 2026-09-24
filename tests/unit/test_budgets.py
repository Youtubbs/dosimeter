"""Budgets stop the next leg, and the session ceiling outlives a turn."""

from __future__ import annotations

import time

import pytest

from dosimeter.config.settings import Bounds
from dosimeter.errors import BudgetError
from dosimeter.harness.budgets import (
    REVIEWER_ITERATIONS,
    SESSION_TOKENS,
    TOOL_INVOCATIONS,
    WALL_CLOCK,
    SessionLedger,
)


def test_a_fresh_ledger_lets_a_leg_start() -> None:
    ledger = SessionLedger(bounds=Bounds())

    assert ledger.check() is None
    ledger.require()


def test_the_tool_cap_stops_the_next_leg() -> None:
    ledger = SessionLedger(bounds=Bounds(max_tool_invocations_per_turn=2))

    ledger.record_tool_invocation()
    assert ledger.check() is None

    ledger.record_tool_invocation()
    breach = ledger.check()

    assert breach is not None
    assert breach.ceiling == TOOL_INVOCATIONS


def test_the_session_ceiling_accumulates_across_two_turns() -> None:
    ledger = SessionLedger(bounds=Bounds(max_session_tokens=1000))

    ledger.record_model_call(input_tokens=400, output_tokens=100)
    ledger.start_turn()
    assert ledger.check() is None

    ledger.record_model_call(input_tokens=400, output_tokens=100)
    breach = ledger.check()

    assert ledger.turn.tokens == 500
    assert ledger.session_tokens == 1000
    assert breach is not None
    assert breach.ceiling == SESSION_TOKENS


def test_a_breach_is_raised_with_the_ceiling_named() -> None:
    ledger = SessionLedger(bounds=Bounds(max_session_tokens=10))
    ledger.record_model_call(input_tokens=10, output_tokens=0)

    with pytest.raises(BudgetError) as caught:
        ledger.require()

    assert caught.value.context["ceiling"] == SESSION_TOKENS


def test_a_breach_becomes_a_partial_response_naming_the_ceiling() -> None:
    ledger = SessionLedger(bounds=Bounds(max_session_tokens=10))
    ledger.record_model_call(input_tokens=11, output_tokens=0)

    breach = ledger.check()
    response = ledger.partial_response(breach, partial="what was drafted so far")

    assert response["status"] == "partial"
    assert response["ceiling"] == SESSION_TOKENS
    assert response["partial"] == "what was drafted so far"


def test_the_reviewer_loop_has_its_own_hard_cap() -> None:
    ledger = SessionLedger(bounds=Bounds(reviewer_iteration_cap=2))

    ledger.record_reviewer_iteration()
    assert ledger.check() is None

    ledger.record_reviewer_iteration()
    breach = ledger.check()

    assert breach is not None
    assert breach.ceiling == REVIEWER_ITERATIONS


def test_the_wall_clock_stops_a_long_turn() -> None:
    ledger = SessionLedger(bounds=Bounds(per_turn_wall_clock_seconds=0.01))
    time.sleep(0.02)

    breach = ledger.check()

    assert breach is not None
    assert breach.ceiling == WALL_CLOCK


def test_retrieval_limits_are_counted() -> None:
    ledger = SessionLedger(bounds=Bounds(max_retrieved_chunks=3, max_retrieved_tokens=100))

    ledger.record_retrieval(chunks=3, tokens=90)
    assert ledger.check() is None

    ledger.record_retrieval(chunks=1, tokens=0)
    assert ledger.check().ceiling == "max_retrieved_chunks"


def test_tokens_left_for_an_agent_respects_both_ceilings() -> None:
    ledger = SessionLedger(bounds=Bounds(max_session_tokens=3000))

    assert ledger.tokens_left_for("coordinator") == 3000
    assert ledger.tokens_left_for("equipment") == 2048

    ledger.record_model_call(input_tokens=2000, output_tokens=0)
    assert ledger.tokens_left_for("coordinator") == 1000

    ledger.record_model_call(input_tokens=1000, output_tokens=0)
    assert ledger.tokens_left_for("coordinator") == 0
    assert ledger.check(agent="coordinator") is not None
