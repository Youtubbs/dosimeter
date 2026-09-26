"""
The checkpointer writes to the application database, one thread per
participant, and a command that starts cold picks up where the last one left
off.
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from dosimeter.config.settings import Bounds, DatabaseSettings
from dosimeter.graph.checkpointer import open_checkpointer, setup_checkpointer
from dosimeter.graph.graph import build_graph
from dosimeter.graph.schemas import Subject, WorkerProposal
from dosimeter.graph.state import initial_state
from dosimeter.graph.threads import Participant, thread_config, thread_id

OFFICER_ID = 7
EXPOSURE = "EXP-2026-0412"

SUBJECT = Subject(
    session_id="session-1",
    officer_id=OFFICER_ID,
    officer_code="OFF-101",
    exposure_id=EXPOSURE,
)


def database_settings() -> DatabaseSettings:
    url = os.environ.get(
        "DOSIMETER_TEST_URL",
        "postgresql+psycopg://dosimeter:dosimeter_local_dev@localhost:55432/dosimeter",
    )
    without_driver = url.replace("postgresql+psycopg://", "")
    credentials, host_part = without_driver.split("@", 1)
    user, password = credentials.split(":", 1)
    host_port, name = host_part.split("/", 1)
    host, port = host_port.split(":", 1)

    return DatabaseSettings(
        _env_file=None,
        host=host,
        port=int(port),
        name=name.split("?", 1)[0],
        user=user,
        use_iam_auth=False,
        password=password,
        sslmode="prefer",
    )


@pytest.fixture
def checkpointed(db: Session):
    """A clean schema with the checkpoint tables created."""

    settings = database_settings()
    setup_checkpointer(settings)
    yield settings


def graph_for(monkeypatch: pytest.MonkeyPatch, participant: Participant, saver):
    """
    The real graph, with an eligibility node that marks which participant wrote
    the state. The Coordinator plans nothing, so every turn goes straight there.
    """

    def node(state):
        return {
            "proposals": {
                participant.value: WorkerProposal(worker=participant.value, kind=participant.value)
            },
            "outcome": f"{participant.value}-ran",
        }

    monkeypatch.setattr("dosimeter.graph.graph.eligibility_node", node)
    return build_graph(Bounds(), checkpointer=saver)


def test_the_checkpoint_tables_live_in_the_application_database(
    checkpointed: DatabaseSettings,
    db: Session,
) -> None:
    tables = set(
        db.scalars(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        ).all()
    )

    assert {"checkpoints", "checkpoint_writes"} <= tables
    assert "exposures" in tables


def test_the_reviewer_state_never_merges_with_a_worker(
    checkpointed: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with open_checkpointer(checkpointed) as saver:
        reviewer_app = graph_for(monkeypatch, Participant.REVIEWER, saver)
        worker_app = graph_for(monkeypatch, Participant.WRITTEN_REPORT, saver)

        reviewer_config = thread_config(OFFICER_ID, EXPOSURE, Participant.REVIEWER, 12)
        worker_config = thread_config(OFFICER_ID, EXPOSURE, Participant.WRITTEN_REPORT, 12)

        reviewer_app.invoke(initial_state(SUBJECT), reviewer_config)
        worker_app.invoke(initial_state(SUBJECT), worker_config)

        reviewer_state = reviewer_app.get_state(reviewer_config).values
        worker_state = worker_app.get_state(worker_config).values

    assert reviewer_state["outcome"] == "reviewer-ran"
    assert worker_state["outcome"] == "written_report-ran"
    assert sorted(reviewer_state["proposals"]) == ["reviewer"]
    assert sorted(worker_state["proposals"]) == ["written_report"]


def test_every_participant_writes_to_its_own_thread(
    checkpointed: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with open_checkpointer(checkpointed) as saver:
        app = graph_for(monkeypatch, Participant.COORDINATOR, saver)

        for participant in Participant:
            app.invoke(
                initial_state(SUBJECT),
                thread_config(OFFICER_ID, EXPOSURE, participant, 12),
            )

        stored = {
            checkpoint.config["configurable"]["thread_id"] for checkpoint in saver.list(None)
        }

    for participant in Participant:
        assert thread_id(OFFICER_ID, EXPOSURE, participant) in stored


def test_a_second_command_starts_cold_and_resumes_from_postgres(
    checkpointed: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = thread_config(OFFICER_ID, EXPOSURE, Participant.COORDINATOR, 12)

    with open_checkpointer(checkpointed) as saver:
        first = graph_for(monkeypatch, Participant.COORDINATOR, saver)
        first.invoke(initial_state(SUBJECT), config)

    with open_checkpointer(checkpointed) as saver:
        second = graph_for(monkeypatch, Participant.COORDINATOR, saver)
        resumed = second.get_state(config)

    assert resumed.values["outcome"] == "coordinator-ran"
    assert resumed.values["subject"].exposure_id == EXPOSURE


def test_a_different_exposure_is_a_different_thread(
    checkpointed: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with open_checkpointer(checkpointed) as saver:
        app = graph_for(monkeypatch, Participant.COORDINATOR, saver)

        app.invoke(initial_state(SUBJECT), thread_config(OFFICER_ID, EXPOSURE, "coordinator", 12))
        other = app.get_state(thread_config(OFFICER_ID, "EXP-2026-0411", "coordinator", 12))

    assert other.values == {}
