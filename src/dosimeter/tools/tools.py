"""
The two read tools that go through the tool API: get_exposure_extraction and
find_similar_exposures.
"""

import logging

from pydantic import BaseModel

from dosimeter.api.schemas import (
    ExposureExtraction,
    FindSimilarExposuresInput,
    GetExposureExtractionInput,
    SimilarExposures,
)
from dosimeter.errors import ExternalServiceError
from dosimeter.graph.schemas import Subject
from dosimeter.tools.dispatcher import Tool, ToolError, ToolErrorCode
from dosimeter.tools.transport import HttpTransport

GET_EXPOSURE_EXTRACTION = "get_exposure_extraction"
FIND_SIMILAR_EXPOSURES = "find_similar_exposures"

logger = logging.getLogger(__name__)


class ApiToolset:
    """Both API-backed tools, and whether they are still available this turn."""

    def __init__(self, transport: HttpTransport) -> None:
        self.transport = transport
        self.disabled: set[str] = set()

    def capabilities_lost(self) -> list[str]:
        return sorted(self.disabled)

    def _unavailable(self, tool_name: str, detail: str) -> ToolError:
        # one unreachable API takes both tools with it; the rest of the turn carries on
        self.disabled.update({GET_EXPOSURE_EXTRACTION, FIND_SIMILAR_EXPOSURES})
        logger.warning(
            "tool.api_unreachable",
            extra={"tool": tool_name, "disabled": self.capabilities_lost(), "detail": detail},
        )
        return ToolError(
            reason_code=ToolErrorCode.UNAVAILABLE,
            message="the tool API is unreachable, so these capabilities are gone for this turn",
            detail={"disabled": self.capabilities_lost(), "reason": detail},
        )

    def get_exposure_extraction(
        self,
        subject: Subject,
        arguments: GetExposureExtractionInput,
    ) -> BaseModel:
        try:
            response = self.transport.get(f"/v1/exposures/{subject.exposure_id}/extraction")
        except ExternalServiceError as error:
            return self._unavailable(GET_EXPOSURE_EXTRACTION, str(error))

        if not response.ok:
            return _error_from(response.status, response.payload)

        return ExposureExtraction.model_validate(response.payload)

    def find_similar_exposures(
        self,
        subject: Subject,
        arguments: FindSimilarExposuresInput,
    ) -> BaseModel:
        path = f"/v1/exposures/{subject.exposure_id}/similar"

        try:
            response = self.transport.post(path, arguments.model_dump())
        except ExternalServiceError as error:
            return self._unavailable(FIND_SIMILAR_EXPOSURES, str(error))

        if not response.ok:
            return _error_from(response.status, response.payload)

        return SimilarExposures.model_validate(response.payload)

    def tools(self) -> list[Tool]:
        return [
            Tool(
                name=GET_EXPOSURE_EXTRACTION,
                description=(
                    "Read the normalized fields cracked from the exposure packet in this "
                    "session, with the Textract confidence for each field."
                ),
                input_model=GetExposureExtractionInput,
                handler=self.get_exposure_extraction,
            ),
            Tool(
                name=FIND_SIMILAR_EXPOSURES,
                description=(
                    "Find earlier exposures whose narrative resembles this one. Returns "
                    "candidates with the outcome each was closed with and the rule that "
                    "decided it. Candidates are evidence, never a conclusion."
                ),
                input_model=FindSimilarExposuresInput,
                handler=self.find_similar_exposures,
            ),
        ]


def _error_from(status: int, payload: dict) -> ToolError:
    reason = payload.get("reason_code", "tool_failed")
    message = payload.get("message", "the tool API refused the call")

    code = ToolErrorCode.INTERNAL
    if status == 403:
        code = ToolErrorCode.DENIED
    elif status == 404:
        code = ToolErrorCode.NOT_FOUND
    elif status == 503:
        code = ToolErrorCode.UNAVAILABLE

    return ToolError(
        reason_code=code,
        message=message,
        detail={"status": status, "api_reason_code": reason},
    )
