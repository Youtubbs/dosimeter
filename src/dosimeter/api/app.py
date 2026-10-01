"""
The tool-backing Flask service.

It is not an officer-facing API: the CLI is the application. Every call carries
its own entitlement check, because a tool that reaches this service must not be
able to read a district its officer holds no grant over.
"""

import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any

from flask import Flask, jsonify, request
from pydantic import BaseModel

from dosimeter.api.identity import resolve_caller
from dosimeter.api.schemas import (
    Denial,
    ExposureExtraction,
    ExtractionField,
    FindSimilarExposuresInput,
    HealthStatus,
    SimilarExposureCandidate,
    SimilarExposures,
)
from dosimeter.config.settings import Settings, get_settings
from dosimeter.logging_config import correlation_scope
from dosimeter.repository import Session, entitlements, queries
from dosimeter.repository.models import EntitlementDenial

SessionFactory = Callable[[], AbstractContextManager[Session]]
Embedder = Callable[[str], list[float]]

NO_IDENTITY = "no_verified_identity"
NOT_FOUND = "exposure_not_found"
EMBEDDING_UNAVAILABLE = "embedding_unavailable"

logger = logging.getLogger(__name__)


def _default_session_factory() -> AbstractContextManager[Session]:
    from dosimeter.repository.connection import session_scope

    return session_scope()


def create_app(
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    embedder: Embedder | None = None,
) -> Flask:
    """Build the service. Everything it talks to is injected."""

    resolved = settings or get_settings()
    open_session = session_factory or _default_session_factory

    app = Flask(__name__)
    app.config["DOSIMETER_SETTINGS"] = resolved

    @contextmanager
    def session() -> Iterator[Session]:
        with open_session() as active:
            yield active

    def caller():
        return resolve_caller(request.headers, resolved)

    @app.get("/health/live")
    def liveness():
        return jsonify(HealthStatus(status="alive").model_dump()), 200

    @app.get("/health/ready")
    def readiness():
        try:
            with session() as active:
                queries.ping(active)
        except Exception as error:  # readiness reports, it never raises
            logger.error("api.readiness_failed", extra={"detail": str(error)})
            payload = HealthStatus(status="not_ready", checks={"database": "unreachable"})
            return jsonify(payload.model_dump()), 503

        payload = HealthStatus(status="ready", checks={"database": "ok"})
        return jsonify(payload.model_dump()), 200

    @app.get("/v1/exposures/<exposure_id>/extraction")
    def get_exposure_extraction(exposure_id: str):
        identity = caller()
        if identity is None:
            return _denied(NO_IDENTITY, "this call carries no verified identity", "unknown")

        with correlation_scope(), session() as active:
            payload, status = extraction_for(active, resolved, identity.officer_code, exposure_id)

        return jsonify(payload.model_dump()), status

    @app.post("/v1/exposures/<exposure_id>/similar")
    def find_similar_exposures(exposure_id: str):
        identity = caller()
        if identity is None:
            return _denied(NO_IDENTITY, "this call carries no verified identity", "unknown")

        arguments = FindSimilarExposuresInput.model_validate(request.get_json(silent=True) or {})

        if embedder is None:
            return jsonify(embedding_unavailable(identity.officer_code).model_dump()), 503

        with correlation_scope(), session() as active:
            payload, status = similar_for(active, identity.officer_code, exposure_id, arguments, embedder)

        return jsonify(payload.model_dump()), status

    @app.get("/openapi.json")
    def openapi():
        return jsonify(openapi_document()), 200

    return app


def extraction_for(
    active: Session, settings: Settings, officer_code: str, exposure_id: str
) -> tuple[BaseModel, int]:
    """The extraction this officer may read, or why not. The Flask route and the MCP tool share it."""

    found = entitlements.exposure_for_officer(active, officer_code, exposure_id)

    if isinstance(found, EntitlementDenial):
        return _denial(found), 403
    if found is None:
        return Denial(reason_code=NOT_FOUND, message="no exposure with that id", officer_code=officer_code), 404

    artifact_by_id = queries.artifact_hashes_by_id(active, exposure_id)
    rows = queries.list_extracted_fields(active, exposure_id)

    floor = settings.confidence_floor
    fields = [
        ExtractionField(
            field_key=row.field_key,
            value=row.value,
            unit=row.unit,
            confidence=row.confidence,
            page=row.page,
            artifact_sha256=artifact_by_id.get(row.artifact_id),
        )
        for row in rows
    ]

    payload = ExposureExtraction(
        exposure_id=found.id,
        district=found.district,
        status=found.status,
        fields=fields,
        low_confidence_field_keys=[
            row.field_key
            for row in rows
            if row.confidence is not None and row.confidence < floor
        ],
    )
    return payload, 200


def similar_for(
    active: Session,
    officer_code: str,
    exposure_id: str,
    arguments: FindSimilarExposuresInput,
    embedder: Embedder,
) -> tuple[BaseModel, int]:
    """Similar exposures in the districts this officer may read, or why not."""

    found = entitlements.exposure_for_officer(active, officer_code, exposure_id)
    if isinstance(found, EntitlementDenial):
        return _denial(found), 403
    if found is None:
        return Denial(reason_code=NOT_FOUND, message="no exposure with that id", officer_code=officer_code), 404

    candidates = entitlements.similar_exposures_for_officer(
        active,
        officer_code,
        embedder(arguments.query_text),
        query_text=arguments.query_text,
        limit=arguments.limit,
    )
    if isinstance(candidates, EntitlementDenial):
        return _denial(candidates), 403

    payload = SimilarExposures(
        candidates=[
            SimilarExposureCandidate(
                exposure_id=item.exposure_id,
                outcome=item.outcome,
                deciding_rule=item.deciding_rule,
                score=item.score,
                narrative_span=item.narrative_span.text,
            )
            for item in candidates
        ]
    )
    return payload, 200


def embedding_unavailable(officer_code: str) -> Denial:
    return Denial(
        reason_code=EMBEDDING_UNAVAILABLE,
        message="this service has no embedding model configured",
        officer_code=officer_code,
    )


def _denied(reason_code: str, message: str, officer_code: str, status: int = 403):
    payload = Denial(reason_code=reason_code, message=message, officer_code=officer_code)
    return jsonify(payload.model_dump()), status


def _denial(denial: EntitlementDenial) -> Denial:
    return Denial(
        reason_code=denial.reason_code,
        message=denial.message,
        officer_code=denial.officer_code,
        district=denial.district,
    )


def openapi_document() -> dict[str, Any]:
    """Generated from the Pydantic models, so it cannot describe a different shape."""

    schemas = {
        name: model.model_json_schema(ref_template="#/components/schemas/{model}")
        for name, model in (
            ("ExposureExtraction", ExposureExtraction),
            ("FindSimilarExposuresInput", FindSimilarExposuresInput),
            ("SimilarExposures", SimilarExposures),
            ("Denial", Denial),
            ("HealthStatus", HealthStatus),
        )
    }

    def body(model_name: str, description: str = "ok") -> dict[str, Any]:
        return {
            "description": description,
            "content": {
                "application/json": {"schema": {"$ref": f"#/components/schemas/{model_name}"}}
            },
        }

    exposure_id = {
        "name": "exposure_id",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
    }

    return {
        "openapi": "3.1.0",
        "info": {"title": "Dosimeter tool API", "version": "1.0.0"},
        "paths": {
            "/health/live": {"get": {"responses": {"200": body("HealthStatus")}}},
            "/health/ready": {
                "get": {"responses": {"200": body("HealthStatus"), "503": body("HealthStatus")}}
            },
            "/v1/exposures/{exposure_id}/extraction": {
                "get": {
                    "operationId": "get_exposure_extraction",
                    "summary": "Read the normalized fields cracked from one exposure packet.",
                    "parameters": [exposure_id],
                    "responses": {
                        "200": body("ExposureExtraction"),
                        "403": body("Denial", "not entitled"),
                        "404": body("Denial", "not found"),
                    },
                }
            },
            "/v1/exposures/{exposure_id}/similar": {
                "post": {
                    "operationId": "find_similar_exposures",
                    "summary": "Find earlier exposures whose narrative resembles this one.",
                    "parameters": [exposure_id],
                    "requestBody": body("FindSimilarExposuresInput", "what to look for"),
                    "responses": {
                        "200": body("SimilarExposures"),
                        "403": body("Denial", "not entitled"),
                    },
                }
            },
        },
        "components": {"schemas": schemas},
    }
