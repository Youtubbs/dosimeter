"""
How a tool reaches the tool API. This is the local stand-in; deployed, the two
tools reach the API through the AgentCore Gateway instead.
"""

import json
import urllib.error
import urllib.request
from typing import Any

from dosimeter.api.identity import VERIFIED_HEADER
from dosimeter.config.settings import get_settings
from dosimeter.errors import ExternalServiceError

# where each read tool lives on the tool API
ROUTES = {
    "get_exposure_extraction": ("GET", "/v1/exposures/{exposure_id}/extraction"),
    "find_similar_exposures": ("POST", "/v1/exposures/{exposure_id}/similar"),
}


class HttpTransport:
    """Calls the tool API over HTTP. Identity travels in the verified header, never in the body."""

    def __init__(
        self,
        base_url: str,
        officer_code: str,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = base_url
        self.officer_code = officer_code
        self.timeout_seconds = (
            timeout_seconds or get_settings().bounds.per_call_http_timeout_seconds
        )

    def call(self, tool: str, exposure_id: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """The JSON the API answered with: the result, or a denial carrying its reason_code."""

        method, path = ROUTES[tool]
        url = f"{self.base_url.rstrip('/')}{path.format(exposure_id=exposure_id)}"
        if not url.startswith(("http://", "https://")):
            raise ExternalServiceError("the tool API url must be http or https", url=url)

        body = json.dumps(arguments or {}).encode("utf-8") if method == "POST" else None
        request = urllib.request.Request(url, data=body, method=method)  # noqa: S310 - scheme checked above
        request.add_header(VERIFIED_HEADER, self.officer_code)
        request.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            # a refusal is an answer too: its body names the reason
            text = error.read().decode("utf-8")
            try:
                return json.loads(text or "{}")
            except json.JSONDecodeError:
                return {"reason_code": "tool_failed", "message": text}
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ExternalServiceError("the tool API is unreachable", detail=str(error)) from error
