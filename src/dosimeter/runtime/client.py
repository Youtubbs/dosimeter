""" running an assess turn on the AgentCore Runtime instead of in the CLI """

import argparse
import json
import logging
import urllib.error
import urllib.request
import uuid
from collections.abc import Sequence
from typing import Any

from dosimeter.aws.aws import cognito_access_token, invoke_agent_runtime
from dosimeter.config.settings import Settings, load_settings
from dosimeter.errors import ConfigurationError, DosimeterError, ExternalServiceError
from dosimeter.harness.assess import AssessResult
from dosimeter.logging_config import configure_logging

SESSION_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"

logger = logging.getLogger(__name__)


def runtime_session_id(officer_code: str, exposure_id: str) -> str:
    """ one Runtime session per officer and exposure. AgentCore needs at least 33 characters """

    return f"dosimeter-{uuid.uuid5(uuid.NAMESPACE_URL, f'{officer_code}:{exposure_id}')}"


def run_assess_on_runtime(settings: Settings, exposure_id: str, officer_code: str) -> AssessResult:
    """ send the turn to the Runtime and read back the same result the CLI would have produced """

    payload: dict[str, Any] = {
        "command": "assess",
        "exposure_id": exposure_id,
        "officer_code": officer_code,
    }

    # through the Gateway the Runtime calls the tools as this officer, so the CLI signs them in
    if settings.tool_transport == "gateway" and settings.identity_client_id and settings.identity_password:
        payload["access_token"] = cognito_access_token(
            officer_code,
            settings.identity_password.get_secret_value(),
            settings.identity_client_id,
        )

    session_id = runtime_session_id(officer_code, exposure_id)
    body = invoke_runtime(settings, payload, session_id)

    if "error" in body:
        raise ExternalServiceError("the Runtime refused the turn", detail=body["error"])

    return AssessResult.model_validate(body)


def invoke_runtime(settings: Settings, payload: dict[str, Any], session_id: str) -> dict[str, Any]:
    """ the deployed Runtime by ARN, or the docker compose stand-in by URL """

    # a whole turn can run up to the wall clock limit, well past the per-call timeout
    wait = settings.bounds.per_turn_wall_clock_seconds + 30

    if settings.runtime_arn:
        return invoke_agent_runtime(
            settings.runtime_arn,
            session_id,
            {**payload, "runtime_arn": settings.runtime_arn},
            read_timeout=wait,
        )

    if settings.runtime_url:
        return _invoke_stand_in(settings.runtime_url, payload, session_id, wait)

    raise ConfigurationError(
        "running on the Runtime needs DOSIMETER_RUNTIME_ARN or DOSIMETER_RUNTIME_URL",
        fields=["runtime_arn", "runtime_url"],
    )


def _invoke_stand_in(url: str, payload: dict[str, Any], session_id: str, wait: float) -> dict[str, Any]:
    """ the stand-in speaks the same contract as the Runtime, over plain HTTP """

    if not url.startswith(("http://", "https://")):
        raise ConfigurationError("the Runtime URL must be http or https", field="runtime_url")

    body = json.dumps({**payload, "runtime_arn": f"stand-in {url}"}).encode()
    request = urllib.request.Request(f"{url.rstrip('/')}/invocations", data=body, method="POST")  # noqa: S310
    request.add_header("Content-Type", "application/json")
    request.add_header(SESSION_HEADER, session_id)

    try:
        with urllib.request.urlopen(request, timeout=wait) as response:  # noqa: S310 - scheme checked above
            return json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ExternalServiceError("the Runtime stand-in is unreachable", detail=str(error)) from error


def main(argv: Sequence[str] | None = None) -> int:
    """ migrate or seed the private RDS database through the workflow Runtime, which sits in its VPC

            python -m dosimeter.runtime.client migrate
    """

    parser = argparse.ArgumentParser(prog="dosimeter-runtime")
    parser.add_argument("command", choices=("migrate", "seed"))
    args = parser.parse_args(argv)

    configure_logging()
    try:
        body = invoke_runtime(load_settings(), {"command": args.command}, f"dosimeter-{args.command}-{uuid.uuid4()}")
    except DosimeterError as error:
        logger.error("runtime.failed", extra={"command": args.command, "detail": str(error)})
        return 1

    if "error" in body:
        logger.error("runtime.failed", extra={"command": args.command, "detail": body["error"]})
        return 1

    logger.info("runtime.done", extra={"command": args.command, "result": body})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
