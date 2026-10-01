"""
the officer asks about an exposure that already has a dossier. The
Coordinator decides whether the earlier conclusions answer it or a worker has to run
(a rule re-run on a hypothetical dose, or a worker the first turn did not dispatch),
and the answer is written from the earlier dossier plus what this turn's rules found.
"""

import json
import logging
import time
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from dosimeter.config.settings import Settings
from dosimeter.errors import EntitlementError
from dosimeter.graph.nodes.eligibility import rule_results
from dosimeter.harness.assess import Turn, run_turn
from dosimeter.harness.dossier import render_dossier
from dosimeter.models.bedrock import REASONING_ROLE, check_budget, get_chat_model, record_usage
from dosimeter.prompts import ASK_SYSTEM_PROMPT
from dosimeter.redaction import redact
from dosimeter.repository import Session, queries

logger = logging.getLogger(__name__)


class AskAnswer(BaseModel):
    """What the model writes back."""

    answer: str = Field(min_length=1)
    citations: list[str] = Field(default_factory=list)


class AskResult(BaseModel):
    exposure_id: str
    run_id: UUID
    answer: str
    citations: list[str]
    workers: list[str]
    rules: list[str]
    duration_seconds: float
    partial: dict | None = None


def _this_turn(turn: Turn) -> str:
    """The proposals and rule results this turn produced, as the answer may quote them."""

    proposals = {name: item.payload for name, item in (turn.state.get("proposals") or {}).items()}
    results = {
        rule_id: {
            key: result.get(key) for key in ("outcome", "inputs_used", "threshold", "explanation")
        }
        for rule_id, result in rule_results(turn.state).items()
    }
    return json.dumps({"proposals": proposals, "rule_results": results}, default=str)


def compose_answer(question: str, previous_dossier: str, turn: Turn) -> AskAnswer:
    """One structured call, under the same budget and run record as the rest of the turn."""

    check_budget(turn.ledger, "ask")

    model = get_chat_model(max_tokens=turn.ledger.tokens_left_for("ask"))
    structured_model = model.with_structured_output(AskAnswer, include_raw=True)

    prompt = redact(
        f"Question: {question}\n\nThe earlier dossier:\n{previous_dossier}\n\nThis turn:\n{_this_turn(turn)}"
    )

    started = time.perf_counter()
    result = structured_model.invoke(
        [SystemMessage(content=ASK_SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )

    usage = getattr(result.get("raw"), "usage_metadata", None) or {}
    record_usage(
        ledger=turn.ledger,
        recorder=turn.recorder,
        agent="ask",
        role=REASONING_ROLE,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        started=started,
    )

    answer = result.get("parsed")
    return answer if isinstance(answer, AskAnswer) else AskAnswer.model_validate(answer)


def run_ask(
    session: Session, exposure_id: str, officer_code: str, question: str, settings: Settings
) -> AskResult:
    """Answer one follow-up question, continuing the officer's session on this exposure."""

    # there has to be an earlier turn to follow up on
    previous_dossier = render_dossier(session, exposure_id)

    officer = queries.officer_by_code(session, officer_code)
    if officer is None:
        raise EntitlementError("no such officer", officer_code=officer_code)

    turn = run_turn(
        session,
        exposure_id,
        officer_code,
        settings,
        command="ask",
        session_id=queries.latest_session(session, officer.id, exposure_id),
        question=question,
        previous_dossier=previous_dossier,
    )

    answer = None
    if turn.partial is None:
        answer = compose_answer(question, previous_dossier, turn)

    outcome = "partial" if answer is None else "answered"
    turn.recorder.finish(outcome)
    queries.end_session(session, turn.session_id)
    session.commit()

    logger.info(
        "ask.completed", extra={"exposure_id": exposure_id, "run_id": str(turn.recorder.run_id)}
    )

    return AskResult(
        exposure_id=exposure_id,
        run_id=turn.recorder.run_id,
        answer=answer.answer if answer else turn.partial["message"],
        citations=answer.citations if answer else [],
        workers=sorted(turn.state.get("proposals") or {}),
        rules=[
            f"{rule_id}: {getattr(result['outcome'], 'value', result['outcome'])}"
            for rule_id, result in sorted(rule_results(turn.state).items())
        ],
        duration_seconds=turn.duration,
        partial=turn.partial,
    )
