"""dosimeter ask: a follow-up turn through the same harness as assess, continuing the session."""

from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from dosimeter.errors import GateError
from dosimeter.graph.checkpointer import setup_checkpointer
from dosimeter.graph.schemas import DispatchPlan
from dosimeter.harness.ask import AskAnswer, run_ask
from dosimeter.harness.assess import run_assess
from dosimeter.repository import queries, seeds
from tests.integration.test_checkpointer import database_settings
from tests.integration.test_run_record import seed_doses, settings_for_tests

EXPOSURE = "EXP-2026-0412"
OFFICER = "OFF-101"


class Recording:
    """A stand-in chat model that answers with one structured object and keeps what it was sent."""

    def __init__(self, parsed) -> None:
        self.parsed = parsed
        self.prompts: list[str] = []

    def with_structured_output(self, schema, include_raw=False):
        return self

    def invoke(self, messages):
        self.prompts.append(messages[-1].content)
        return {
            "raw": SimpleNamespace(usage_metadata={"input_tokens": 50, "output_tokens": 20}),
            "parsed": self.parsed,
        }


@pytest.fixture
def assessed(db: Session, monkeypatch: pytest.MonkeyPatch) -> Recording:
    """An exposure with a dossier from an earlier assess, and a Coordinator that dispatches nothing."""

    seeds.apply_seeds(db)
    seed_doses(db)
    db.commit()
    setup_checkpointer(database_settings())

    coordinator = Recording(DispatchPlan(workers=[], rationale="the dossier answers it"))
    monkeypatch.setattr("dosimeter.graph.nodes.coordinator.get_chat_model", lambda **_: coordinator)
    monkeypatch.setattr(
        "dosimeter.harness.ask.get_chat_model",
        lambda **_: Recording(
            AskAnswer(answer="R1 found notification required on the shallow dose.")
        ),
    )

    run_assess(db, EXPOSURE, OFFICER, settings_for_tests())
    return coordinator


def test_ask_needs_a_dossier_to_follow_up_on(db: Session) -> None:
    seeds.apply_seeds(db)
    db.commit()

    with pytest.raises(GateError, match="run assess first"):
        run_ask(db, EXPOSURE, OFFICER, "why?", settings_for_tests())


def test_ask_continues_the_session_and_plans_from_the_question_and_the_dossier(
    db: Session, assessed: Recording
) -> None:
    first_dossier = queries.latest_dossier(db, EXPOSURE).id
    assess_session = queries.latest_session(db, queries.officer_by_code(db, OFFICER).id, EXPOSURE)

    result = run_ask(db, EXPOSURE, OFFICER, "Why is a telephone call owed?", settings_for_tests())

    record = queries.get_run_record(db, result.run_id)
    assert result.answer == "R1 found notification required on the shallow dose."
    assert result.workers == []
    assert record.command == "ask"
    # the follow-up spends against the same session ceiling as the assess it follows
    assert record.session_id == assess_session
    # the Coordinator saw the question and what the earlier turn concluded
    assert "Why is a telephone call owed?" in assessed.prompts[-1]
    assert "dossier for EXP-2026-0412" in assessed.prompts[-1]
    # an answer is not a new dossier
    assert queries.latest_dossier(db, EXPOSURE).id == first_dossier
