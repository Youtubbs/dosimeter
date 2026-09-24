"""
The tool-backing Flask service.

It is not an officer-facing API: the CLI is the application. Every call carries
its own entitlement check, because a tool that reaches this service must not be
able to read a district its officer holds no grant over.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any

from flask import Flask, jsonify, request

from dosimeter.api.identity import resolve_caller
from dosimeter.api.schemas import (
    Denial,
    ExposureExtraction,
    ExtractionField,
    FindSimilarExposuresInput,
    GetExposureExtractionInput,
    HealthStatus,
    SimilarExposureCandidate,
    SimilarExposures,
)
from dosimeter.config.settings import Settings, get_settings
from dosimeter.logging_config import correlation_scope, get_logger
from dosimeter.repository import Session, entitlements, queries
from dosimeter.repository.models import EntitlementDenial

SessionFactory = Callable[[], AbstractContextManager[Session]]
Embedder = Callable[[str], list[float]]

NO_IDENTITY = "no_verified_identity"
NOT_FOUND = "exposure_not_found"
EMBEDDING_UNAVAILABLE = "embedding_unavailable"

_LOGGER = get_logger(__name__)


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
            _LOGGER.error("api.readiness_failed", extra={"detail": str(error)})
            payload = HealthStatus(status="not_ready", checks={"database": "unreachable"})
            return jsonify(payload.model_dump()), 503

        payload = HealthStatus(status="ready", checks={"database": "ok"})
        return jsonify(payload.model_dump()), 200

    @app.get("/v1/exposures/<exposure_id>/extraction")
    def get_exposure_extraction(exposure_id: str):
        identity = caller()
        if identity is None:
            return _denied(NO_IDENTITY, "this call carries no verified identity", "unknown")

        arguments = GetExposureExtractionInput.model_validate(
            {"include_low_confidence": request.args.get("include_low_confidence", "true") != "false"}
        )

        with correlation_scope(), session() as active:
            found = entitlements.exposure_for_officer(active, identity.officer_code, exposure_id)

            if isinstance(found, EntitlementDenial):
                return _denial_response(found)
            if found is None:
                return _denied(NOT_FOUND, "no exposure with that id", identity.officer_code, 404)

            artifact_by_id = queries.artifact_hashes_by_id(active, exposure_id)
            rows = queries.list_extracted_fields(active, exposure_id)

            floor = resolved.confidence_floor
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
                if arguments.include_low_confidence
                or row.confidence is None
                or row.confidence >= floor
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

        return jsonify(payload.model_dump()), 200

    @app.post("/v1/exposures/<exposure_id>/similar")
    def find_similar_exposures(exposure_id: str):
        identity = caller()
        if identity is None:
            return _denied(NO_IDENTITY, "this call carries no verified identity", "unknown")

        arguments = FindSimilarExposuresInput.model_validate(request.get_json(silent=True) or {})

        if embedder is None:
            return (
                jsonify(
                    Denial(
                        reason_code=EMBEDDING_UNAVAILABLE,
                        message="this service has no embedding model configured",
                        officer_code=identity.officer_code,
                    ).model_dump()
                ),
                503,
            )

        with correlation_scope(), session() as active:
            found = entitlements.exposure_for_officer(active, identity.officer_code, exposure_id)
            if isinstance(found, EntitlementDenial):
                return _denial_response(found)
            if found is None:
                return _denied(NOT_FOUND, "no exposure with that id", identity.officer_code, 404)

            candidates = entitlements.similar_exposures_for_officer(
                active,
                identity.officer_code,
                embedder(arguments.query_text),
                query_text=arguments.query_text,
                limit=arguments.limit,
            )
            if isinstance(candidates, EntitlementDenial):
                return _denial_response(candidates)

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

        return jsonify(payload.model_dump()), 200

    @app.get("/openapi.json")
    def openapi():
        return jsonify(openapi_document()), 200

    return app


def _denied(reason_code: str, message: str, officer_code: str, status: int = 403):
    payload = Denial(reason_code=reason_code, message=message, officer_code=officer_code)
    return jsonify(payload.model_dump()), status


def _denial_response(denial: EntitlementDenial):
    payload = Denial(
        reason_code=denial.reason_code,
        message=denial.message,
        officer_code=denial.officer_code,
        district=denial.district,
    )
    return jsonify(payload.model_dump()), 403


def openapi_document() -> dict[str, Any]:
    """Generated from the Pydantic models, so it cannot describe a different shape."""

    schemas = {
        name: model.model_json_schema(ref_template="#/components/schemas/{model}")
        for name, model in (
            ("GetExposureExtractionInput", GetExposureExtractionInput),
            ("ExposureExtraction", ExposureExtraction),
            ("FindSimilarExposuresInput", FindSimilarExposuresInput),
            ("SimilarExposures", SimilarExposures),
            ("Denial", Denial),
            ("HealthStatus", HealthStatus),
        )
    }

    json_response = {
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Denial"}}}
    }

    def ok(model_name: str) -> dict[str, Any]:
        return {
            "description": "ok",
            "content": {
                "application/json": {"schema": {"$ref": f"#/components/schemas/{model_name}"}}
            },
        }

    return {
        "openapi": "3.1.0",
        "info": {"title": "Dosimeter tool API", "version": "1.0.0"},
        "paths": {
            "/health/live": {"get": {"responses": {"200": ok("HealthStatus")}}},
            "/health/ready": {
                "get": {"responses": {"200": ok("HealthStatus"), "503": ok("HealthStatus")}}
            },
            "/v1/exposures/{exposure_id}/extraction": {
                "get": {
                    "parameters": [
                        {
                            "name": "exposure_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": ok("ExposureExtraction"),
                        "403": {"description": "not entitled", **json_response},
                        "404": {"description": "not found", **json_response},
                    },
                }
            },
            "/v1/exposures/{exposure_id}/similar": {
                "post": {
                    "parameters": [
                        {
                            "name": "exposure_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/FindSimilarExposuresInput"
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": ok("SimilarExposures"),
                        "403": {"description": "not entitled", **json_response},
                    },
                }
            },
        },
        "components": {"schemas": schemas},
    }
