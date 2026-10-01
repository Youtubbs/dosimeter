"""
The two read tools that go through the tool API: get_exposure_extraction and
find_similar_exposures.
"""

import logging
from typing import Any

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

# the API's refusals, by the reason code its body carries
DENIED = {"no_verified_identity", "unknown_officer", "no_grants", "district_not_granted"}
CODE_FOR_REASON = {
    "exposure_not_found": ToolErrorCode.NOT_FOUND,
    "embedding_unavailable": ToolErrorCode.UNAVAILABLE,
}

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

    def _call(
        self,
        tool_name: str,
        subject: Subject,
        output_model: type[BaseModel],
        arguments: dict[str, Any] | None = None,
    ) -> BaseModel:
        try:
            payload = self.transport.call(tool_name, subject.exposure_id, arguments)
        except ExternalServiceError as error:
            return self._unavailable(tool_name, str(error))

        if "reason_code" in payload:
            return _error_from(payload)

        return output_model.model_validate(payload)

    def get_exposure_extraction(
        self,
        subject: Subject,
        arguments: GetExposureExtractionInput,
    ) -> BaseModel:
        return self._call(GET_EXPOSURE_EXTRACTION, subject, ExposureExtraction)

    def find_similar_exposures(
        self,
        subject: Subject,
        arguments: FindSimilarExposuresInput,
    ) -> BaseModel:
        return self._call(FIND_SIMILAR_EXPOSURES, subject, SimilarExposures, arguments.model_dump())

    def tools(self) -> list[Tool]:
        return [
            Tool(
                name=GET_EXPOSURE_EXTRACTION,
                description=(
                    "Read the normalized fields cracked from the exposure packet in this "
                    "session, with the Textract confidence for each field."
                ),
                input_model=GetExposureExtractionInput,
                output_model=ExposureExtraction,
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
                output_model=SimilarExposures,
                handler=self.find_similar_exposures,
            ),
        ]


def _error_from(payload: dict) -> ToolError:
    reason = payload.get("reason_code", "tool_failed")

    return ToolError(
        reason_code=ToolErrorCode.DENIED
        if reason in DENIED
        else CODE_FOR_REASON.get(reason, ToolErrorCode.INTERNAL),
        message=payload.get("message", "the tool API refused the call"),
        detail={"api_reason_code": reason},
    )
