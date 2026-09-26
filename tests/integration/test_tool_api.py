"""The tool API and the two clients that call it, against a real database."""

from contextlib import contextmanager
from datetime import date
from typing import Any

import pytest
from sqlalchemy.orm import Session

from dosimeter.api.app import create_app, openapi_document
from dosimeter.api.identity import VERIFIED_HEADER
from dosimeter.api.schemas import ExposureExtraction, FindSimilarExposuresInput
from dosimeter.config.settings import Bounds, Settings
from dosimeter.graph.schemas import Subject
from dosimeter.harness.budgets import SessionLedger
from dosimeter.repository import orm, queries, seeds
from dosimeter.repository.models import Artifact, ExtractedField, HistoricalExposure
from dosimeter.tools.dispatcher import ToolDispatcher, ToolErrorCode, build_registry
from dosimeter.tools.tools import ApiToolset
from dosimeter.tools.transport import TransportResponse

EXPOSURE = "EXP-2026-0412"
OWNED_ONLY_BY_OFF_103 = "EXP-2026-0414"
DIMENSIONS = orm.EMBEDDING_DIMENSIONS


def settings_for_tests(dev_identity: bool = False) -> Settings:
    return Settings(
        _env_file=None,
        bedrock_model_id="text-model-id",
        bedrock_embed_model_id="embedding-model-id",
        knowledge_base_id="kb",
        guardrail_id="gr",
        corpus_bucket="corpus",
        packet_bucket="packets",
        tool_api_dev_identity=dev_identity,
    )


class FlaskClientTransport:
    """The HttpTransport interface over a Flask test client, so the tools call the real app."""

    def __init__(self, client: Any, officer_code: str) -> None:
        self.client = client
        self.officer_code = officer_code

    def get(self, path: str) -> TransportResponse:
        response = self.client.get(path, headers={VERIFIED_HEADER: self.officer_code})
        return TransportResponse(status=response.status_code, payload=response.get_json() or {})

    def post(self, path: str, body: dict[str, Any] | None = None) -> TransportResponse:
        response = self.client.post(path, json=body or {}, headers={VERIFIED_HEADER: self.officer_code})
        return TransportResponse(status=response.status_code, payload=response.get_json() or {})


def embedding(seed: float) -> list[float]:
    return [seed] + [0.0] * (DIMENSIONS - 1)


def seed_extraction(db: Session) -> None:
    seeds.apply_seeds(db)
    artifact_id = queries.insert_artifact(
        db,
        Artifact(
            exposure_id=EXPOSURE,
            kind="exposure-report",
            content_sha256="a" * 64,
            s3_bucket="packets",
            s3_key="artifacts/aa/" + "a" * 64 + ".pdf",
            status="stored",
        ),
    )
    queries.insert_extracted_fields(
        db,
        [
            ExtractedField(
                exposure_id=EXPOSURE,
                artifact_id=artifact_id,
                field_key="Total Effective Dose Equivalent",
                value="4.1",
                unit="rem",
                confidence=0.99,
                page=1,
            ),
            ExtractedField(
                exposure_id=EXPOSURE,
                artifact_id=artifact_id,
                field_key="Shallow Dose Equivalent",
                value="310",
                unit="rad",
                confidence=0.42,
                page=1,
            ),
        ],
    )
    queries.insert_historical_exposure(
        db,
        HistoricalExposure(
            exposure_id="hist-0001",
            worker_id="WKR-1047",
            district="District 2",
            occurred_on=date(2025, 4, 2),
            outcome="notification_required",
            deciding_rule="R1",
            narrative="The source assembly would not retract. The crew withdrew and surveyed.",
        ),
        embedding=embedding(1.0),
    )
    db.commit()


@pytest.fixture
def client(db: Session):
    seed_extraction(db)

    @contextmanager
    def session_factory():
        yield db

    app = create_app(
        settings=settings_for_tests(),
        session_factory=session_factory,
        embedder=lambda text: embedding(1.0),
    )
    app.config.update(TESTING=True)
    return app.test_client()


def headers(officer_code: str) -> dict[str, str]:
    return {VERIFIED_HEADER: officer_code}


def test_liveness_needs_nothing(client) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.get_json()["status"] == "alive"


def test_readiness_checks_the_database(client) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.get_json()["checks"]["database"] == "ok"


def test_readiness_reports_a_database_it_cannot_reach() -> None:
    @contextmanager
    def broken_factory():
        raise RuntimeError("no database")
        yield

    app = create_app(settings=settings_for_tests(), session_factory=broken_factory)
    app.config.update(TESTING=True)

    response = app.test_client().get("/health/ready")

    assert response.status_code == 503
    assert response.get_json()["checks"]["database"] == "unreachable"


def test_an_entitled_officer_reads_the_extraction(client) -> None:
    response = client.get(f"/v1/exposures/{EXPOSURE}/extraction", headers=headers("OFF-101"))

    payload = ExposureExtraction.model_validate(response.get_json())

    assert response.status_code == 200
    assert payload.district == "District 2"
    assert {field.field_key for field in payload.fields} == {
        "Total Effective Dose Equivalent",
        "Shallow Dose Equivalent",
    }
    assert payload.low_confidence_field_keys == ["Shallow Dose Equivalent"]
    assert payload.fields[0].artifact_sha256 == "a" * 64


def test_an_officer_without_the_district_gets_a_denial_not_an_empty_list(client) -> None:
    response = client.get(
        f"/v1/exposures/{OWNED_ONLY_BY_OFF_103}/extraction",
        headers=headers("OFF-101"),
    )

    assert response.status_code == 403
    assert response.get_json()["reason_code"] == "district_not_granted"


def test_the_owning_officer_reads_the_exposure_nobody_else_can(client) -> None:
    response = client.get(
        f"/v1/exposures/{OWNED_ONLY_BY_OFF_103}/extraction",
        headers=headers("OFF-103"),
    )

    assert response.status_code == 200


def test_an_officer_with_no_grant_at_all_is_denied(client) -> None:
    response = client.get(f"/v1/exposures/{EXPOSURE}/extraction", headers=headers("OFF-104"))

    assert response.status_code == 403
    assert response.get_json()["reason_code"] == "no_grants"


def test_a_call_with_no_verified_identity_is_refused(client) -> None:
    response = client.get(f"/v1/exposures/{EXPOSURE}/extraction")

    assert response.status_code == 403
    assert response.get_json()["reason_code"] == "no_verified_identity"


def test_identity_is_never_taken_from_the_query_or_the_body(client) -> None:
    response = client.get(
        f"/v1/exposures/{EXPOSURE}/extraction",
        query_string={"officer_code": "OFF-101"},
    )

    assert response.status_code == 403
    assert response.get_json()["reason_code"] == "no_verified_identity"


def test_the_dev_stub_header_only_works_when_it_is_switched_on(db: Session) -> None:
    seed_extraction(db)

    @contextmanager
    def session_factory():
        yield db

    off = create_app(settings=settings_for_tests(dev_identity=False), session_factory=session_factory)
    on = create_app(settings=settings_for_tests(dev_identity=True), session_factory=session_factory)

    stub = {"X-Dosimeter-Officer": "OFF-101"}

    assert off.test_client().get(f"/v1/exposures/{EXPOSURE}/extraction", headers=stub).status_code == 403
    assert on.test_client().get(f"/v1/exposures/{EXPOSURE}/extraction", headers=stub).status_code == 200


def test_similar_exposures_come_back_as_candidates(client) -> None:
    response = client.post(
        f"/v1/exposures/{EXPOSURE}/similar",
        json={"query_text": "source would not retract", "limit": 3},
        headers=headers("OFF-101"),
    )

    payload = response.get_json()

    assert response.status_code == 200
    assert payload["candidates"][0]["exposure_id"] == "hist-0001"
    assert payload["candidates"][0]["deciding_rule"] == "R1"
    assert "retract" in payload["candidates"][0]["narrative_span"]
    assert "conclusion" not in payload


def test_the_openapi_document_is_built_from_the_tool_models(client) -> None:
    response = client.get("/openapi.json")
    document = response.get_json()

    assert response.status_code == 200
    assert document == openapi_document()
    assert (
        document["components"]["schemas"]["FindSimilarExposuresInput"]["properties"].keys()
        == FindSimilarExposuresInput.model_json_schema()["properties"].keys()
    )


def dispatcher_for(client, officer_code: str) -> tuple[ToolDispatcher, ApiToolset]:
    toolset = ApiToolset(transport=FlaskClientTransport(client=client, officer_code=officer_code))
    dispatcher = ToolDispatcher(
        registry=build_registry(toolset.tools()),
        ledger=SessionLedger(bounds=Bounds()),
        subject=Subject(
            session_id="session-1",
            officer_id=1,
            officer_code=officer_code,
            exposure_id=EXPOSURE,
        ),
    )
    return dispatcher, toolset


def test_the_extraction_tool_reads_through_the_api(client) -> None:
    dispatcher, _ = dispatcher_for(client, "OFF-101")

    response = dispatcher.invoke("get_exposure_extraction", {})

    assert response.ok
    assert response.value["exposure_id"] == EXPOSURE


def test_the_similarity_tool_returns_candidates_only(client) -> None:
    dispatcher, _ = dispatcher_for(client, "OFF-101")

    response = dispatcher.invoke(
        "find_similar_exposures",
        {"query_text": "source would not retract", "limit": 2},
    )

    assert response.ok
    candidate = response.value["candidates"][0]
    assert set(candidate) == {
        "exposure_id",
        "outcome",
        "deciding_rule",
        "score",
        "narrative_span",
    }


def test_an_unentitled_tool_call_surfaces_the_api_denial(client) -> None:
    dispatcher, _ = dispatcher_for(client, "OFF-104")

    response = dispatcher.invoke("get_exposure_extraction", {})

    assert not response.ok
    assert response.error.reason_code == ToolErrorCode.DENIED
    assert response.error.detail["api_reason_code"] == "no_grants"
