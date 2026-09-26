"""
How a tool reaches the tool API. This is the local stand-in; deployed, the two
tools reach the API through the AgentCore Gateway instead.
"""

import json
import urllib.error
import urllib.request
from typing import Any

from pydantic import BaseModel

from dosimeter.api.identity import VERIFIED_HEADER
from dosimeter.errors import ExternalServiceError


class TransportResponse(BaseModel):
    """A status code and a decoded body, whatever carried them."""

    status: int
    payload: dict[str, Any]

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class HttpTransport:
    """Calls the tool API over HTTP. Identity travels in the verified header, never in the body."""

    def __init__(self, base_url: str, officer_code: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url
        self.officer_code = officer_code
        self.timeout_seconds = timeout_seconds

    def _send(self, request: urllib.request.Request) -> TransportResponse:
        if request.type not in ("http", "https"):
            raise ExternalServiceError("the tool API url must be http or https", url=request.full_url)

        request.add_header(VERIFIED_HEADER, self.officer_code)
        request.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - scheme checked above
                body = response.read().decode("utf-8")
                return TransportResponse(status=response.status, payload=json.loads(body or "{}"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            try:
                payload = json.loads(body or "{}")
            except json.JSONDecodeError:
                payload = {"message": body}
            return TransportResponse(status=error.code, payload=payload)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ExternalServiceError("the tool API is unreachable", detail=str(error)) from error

    def get(self, path: str) -> TransportResponse:
        url = f"{self.base_url.rstrip('/')}{path}"
        return self._send(urllib.request.Request(url, method="GET"))  # noqa: S310

    def post(self, path: str, body: dict[str, Any] | None = None) -> TransportResponse:
        url = f"{self.base_url.rstrip('/')}{path}"
        payload = json.dumps(body or {}).encode("utf-8")
        request = urllib.request.Request(url, data=payload, method="POST")  # noqa: S310
        request.add_header("Content-Type", "application/json")
        return self._send(request)
