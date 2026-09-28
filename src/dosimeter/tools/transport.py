"""
How a tool reaches the tool API.

The AgentCore Gateway swaps in behind the same interface later.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from dosimeter.api.identity import VERIFIED_HEADER
from dosimeter.errors import ExternalServiceError


class TransportResponse:
    """A status code and a decoded body, whatever carried them."""

    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status = status
        self.payload = payload

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class Transport(Protocol):
    def get(self, path: str, params: dict[str, Any] | None = None) -> TransportResponse: ...

    def post(self, path: str, body: dict[str, Any] | None = None) -> TransportResponse: ...


@dataclass
class HttpTransport:
    """The real one. Identity travels in the verified header, never in the body."""

    base_url: str
    officer_code: str
    timeout_seconds: float = 30.0

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        url = f"{self.base_url.rstrip('/')}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        return url

    def _send(self, request: urllib.request.Request) -> TransportResponse:
        if request.type not in ("http", "https"):
            raise ExternalServiceError(
                "the tool API url must be http or https", url=request.full_url
            )

        request.add_header(VERIFIED_HEADER, self.officer_code)
        request.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - scheme checked above
                body = response.read().decode("utf-8")
                return TransportResponse(response.status, json.loads(body or "{}"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            try:
                payload = json.loads(body or "{}")
            except json.JSONDecodeError:
                payload = {"message": body}
            return TransportResponse(error.code, payload)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ExternalServiceError("the tool API is unreachable", detail=str(error)) from error

    def get(self, path: str, params: dict[str, Any] | None = None) -> TransportResponse:
        return self._send(urllib.request.Request(self._url(path, params), method="GET"))  # noqa: S310

    def post(self, path: str, body: dict[str, Any] | None = None) -> TransportResponse:
        payload = json.dumps(body or {}).encode("utf-8")
        request = urllib.request.Request(self._url(path), data=payload, method="POST")  # noqa: S310
        request.add_header("Content-Type", "application/json")
        return self._send(request)


@dataclass
class FlaskClientTransport:
    """The same interface over a Flask test client, for tests and local runs."""

    client: Any
    officer_code: str

    def _headers(self) -> dict[str, str]:
        return {VERIFIED_HEADER: self.officer_code}

    def get(self, path: str, params: dict[str, Any] | None = None) -> TransportResponse:
        response = self.client.get(path, query_string=params or {}, headers=self._headers())
        return TransportResponse(response.status_code, response.get_json() or {})

    def post(self, path: str, body: dict[str, Any] | None = None) -> TransportResponse:
        response = self.client.post(path, json=body or {}, headers=self._headers())
        return TransportResponse(response.status_code, response.get_json() or {})
