"""creating the boto3 client that will connect to aws w our credentials an return running sessions"""

import json
from collections.abc import Generator
from functools import lru_cache
from typing import Any

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from dosimeter.config.settings import DatabaseSettings, get_settings
from dosimeter.errors import ExternalServiceError


@lru_cache(maxsize=1)
def get_session() -> boto3.Session:
    """
    ONE SHARED AWS session for the entire app
    """

    settings = get_settings()
    return boto3.Session(profile_name=settings.aws_profile, region_name=settings.aws_region)


@lru_cache(maxsize=1)
def client_config() -> Config:
    """every AWS call gives up after the per-call HTTP timeout from settings"""

    timeout = get_settings().bounds.per_call_http_timeout_seconds
    return Config(connect_timeout=timeout, read_timeout=timeout)


@lru_cache(maxsize=None)
def get_client(service_name: str, read_timeout: float | None = None):
    """return a boto3 client. a call that runs a whole turn can wait longer than the per-call timeout"""

    config = client_config()
    if read_timeout is not None:
        config = config.merge(Config(read_timeout=read_timeout))

    return get_session().client(service_name, config=config)


def cognito_access_token(username: str, password: str, client_id: str) -> str:
    """sign an officer in to the Cognito user pool the Gateway trusts, and return the access token"""

    response = get_client("cognito-idp").initiate_auth(
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": username, "PASSWORD": password},
    )
    return response["AuthenticationResult"]["AccessToken"]


def invoke_agent_runtime(
    runtime_arn: str, session_id: str, payload: dict[str, Any], read_timeout: float
) -> dict[str, Any]:
    """send one payload to a deployed AgentCore Runtime and read back its JSON answer"""

    try:
        response = get_client("bedrock-agentcore", read_timeout=read_timeout).invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            runtimeSessionId=session_id,
            contentType="application/json",
            accept="application/json",
            payload=json.dumps(payload).encode(),
        )

        # `response` is a streaming body; read it once.
        return json.loads(response["response"].read().decode())
    except (BotoCoreError, ClientError) as error:
        raise ExternalServiceError(
            "the AgentCore Runtime call failed", detail=str(error)
        ) from error


def rds_auth_token(database: DatabaseSettings) -> str:
    """a fresh IAM password for the database user. signed locally, and good for 15 minutes"""

    return get_client("rds").generate_db_auth_token(
        DBHostname=database.host,
        Port=database.port,
        DBUsername=database.user,
    )


# specifies the 'signingName' SigV4 uses
SIGNING_SERVICE = "bedrock-agentcore"

# a few headers that httpx sets that we DO NOT want SigV4 to sign
UNSIGNABLE = {"connection", "host", "content-length"}


class SigV4HttpxAuth(httpx.Auth):
    """signs each request to an AWS_IAM Gateway with our credentials (the execution role when deployed)"""

    # the body is part of the signature, so httpx must load it first
    requires_request_body = True

    def __init__(self, credentials=None, region: str | None = None) -> None:
        credentials = credentials or get_session().get_credentials()

        if credentials is None:
            raise RuntimeError(
                "No AWS credentials. Locally, set AWS_PROFILE. Deployed, the execution role failed to resolve."
            )

        self._signer = SigV4Auth(credentials, SIGNING_SERVICE, region or get_settings().aws_region)

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        aws_request = AWSRequest(
            method=request.method,
            url=str(request.url),
            data=request.content or "",
            headers={
                key: value
                for key, value in request.headers.items()
                if key.lower() not in UNSIGNABLE
            },
        )

        # copy the Authorization, X-Amz-Date and X-Amz-Security-Token headers back onto the request
        self._signer.add_auth(aws_request)
        for key, value in aws_request.headers.items():
            request.headers[key] = value

        yield request
