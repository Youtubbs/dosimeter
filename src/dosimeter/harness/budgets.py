"""
Bounds on a turn and on a session. Every limit is checked before a leg starts
and the usage is added after it finishes, so a leg never begins on a budget
that is already spent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from dosimeter.config.settings import Bounds
from dosimeter.errors import BudgetError

TOKENS_PER_CALL = "max_tokens_per_call"
TOOL_INVOCATIONS = "max_tool_invocations_per_turn"
RECURSION_DEPTH = "max_recursion_depth"
RETRIEVED_CHUNKS = "max_retrieved_chunks"
RETRIEVED_TOKENS = "max_retrieved_tokens"
WALL_CLOCK = "per_turn_wall_clock_seconds"
SESSION_TOKENS = "max_session_tokens"
REVIEWER_ITERATIONS = "reviewer_iteration_cap"


@dataclass
class TurnUsage:
    """What one turn has spent so far."""

    tool_invocations: int = 0
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    retrieved_chunks: int = 0
    retrieved_tokens: int = 0
    reviewer_iterations: int = 0
    started_at: float = field(default_factory=time.monotonic)

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at


@dataclass
class BudgetBreach:
    """A limit that has been reached, named so the caller can say which."""

    ceiling: str
    limit: float
    used: float

    @property
    def message(self) -> str:
        return f"{self.ceiling} reached: {self.used} of {self.limit}"


class SessionLedger:
    """
    Usage for one exposure session. Turns come and go; the ledger outlives them,
    which is what makes the session ceiling accumulate across assess and ask.
    """

    def __init__(self, bounds: Bounds, clock: object | None = None) -> None:
        self.bounds = bounds
        self.session_input_tokens = 0
        self.session_output_tokens = 0
        self.turn = TurnUsage()
        self._clock = clock

    @property
    def session_tokens(self) -> int:
        return self.session_input_tokens + self.session_output_tokens

    def start_turn(self) -> TurnUsage:
        """Begin a fresh turn. Session totals carry over; turn totals do not."""

        self.turn = TurnUsage()
        return self.turn

    def check(self, *, agent: str | None = None) -> BudgetBreach | None:
        """The first ceiling that is spent, or None when the leg may start."""

        if self.session_tokens >= self.bounds.max_session_tokens:
            return BudgetBreach(SESSION_TOKENS, self.bounds.max_session_tokens, self.session_tokens)

        if self.turn.tool_invocations >= self.bounds.max_tool_invocations_per_turn:
            return BudgetBreach(
                TOOL_INVOCATIONS,
                self.bounds.max_tool_invocations_per_turn,
                self.turn.tool_invocations,
            )

        if self.turn.retrieved_chunks > self.bounds.max_retrieved_chunks:
            return BudgetBreach(
                RETRIEVED_CHUNKS, self.bounds.max_retrieved_chunks, self.turn.retrieved_chunks
            )

        if self.turn.retrieved_tokens > self.bounds.max_retrieved_tokens:
            return BudgetBreach(
                RETRIEVED_TOKENS, self.bounds.max_retrieved_tokens, self.turn.retrieved_tokens
            )

        if self.turn.reviewer_iterations >= self.bounds.reviewer_iteration_cap:
            return BudgetBreach(
                REVIEWER_ITERATIONS,
                self.bounds.reviewer_iteration_cap,
                self.turn.reviewer_iterations,
            )

        elapsed = self.turn.elapsed_seconds
        if elapsed >= self.bounds.per_turn_wall_clock_seconds:
            return BudgetBreach(WALL_CLOCK, self.bounds.per_turn_wall_clock_seconds, elapsed)

        if agent is not None and self.tokens_left_for(agent) <= 0:
            return BudgetBreach(TOKENS_PER_CALL, self.bounds.tokens_for(agent), self.turn.tokens)

        return None

    def require(self, *, agent: str | None = None) -> None:
        """Raise when a leg may not start, naming the ceiling that stopped it."""

        breach = self.check(agent=agent)
        if breach is not None:
            raise BudgetError(breach.message, ceiling=breach.ceiling, limit=breach.limit)

    def tokens_left_for(self, agent: str) -> int:
        """What the agent may still spend this session, capped by its per-call limit."""

        session_left = self.bounds.max_session_tokens - self.session_tokens
        return min(self.bounds.tokens_for(agent), max(session_left, 0))

    def record_model_call(self, input_tokens: int, output_tokens: int) -> None:
        self.turn.model_calls += 1
        self.turn.input_tokens += input_tokens
        self.turn.output_tokens += output_tokens
        self.session_input_tokens += input_tokens
        self.session_output_tokens += output_tokens

    def record_tool_invocation(self) -> None:
        self.turn.tool_invocations += 1

    def record_retrieval(self, chunks: int, tokens: int) -> None:
        self.turn.retrieved_chunks += chunks
        self.turn.retrieved_tokens += tokens

    def record_reviewer_iteration(self) -> None:
        self.turn.reviewer_iterations += 1

    def partial_response(self, breach: BudgetBreach, partial: str = "") -> dict[str, object]:
        """What a caller returns instead of finishing, when a ceiling stops it."""

        return {
            "status": "partial",
            "ceiling": breach.ceiling,
            "limit": breach.limit,
            "used": breach.used,
            "message": breach.message,
            "partial": partial,
        }
