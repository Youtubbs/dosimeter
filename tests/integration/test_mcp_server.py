"""The read tools over MCP, end to end: the Gateway transport, the MCP server, the verified token and Postgres."""

import socket
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace

import jwt
import pytest
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.orm import Session

from dosimeter.api import mcp_server
from dosimeter.api.identity import cognito_issuer
from dosimeter.config.settings import Bounds
from dosimeter.graph.schemas import Subject
from dosimeter.harness.budgets import SessionLedger
from dosimeter.tools.dispatcher import ToolDispatcher, ToolErrorCode, build_registry
from dosimeter.tools.gateway import GatewayTransport
from dosimeter.tools.tools import ApiToolset

from tests.integration.test_tool_api import EXPOSURE, embedding, seed_extraction, settings_for_tests

CLIENT_ID = "client-123"
SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SETTINGS = settings_for_tests().model_copy(
    update={"identity_user_pool_id": "us-east-1_TestPool", "identity_client_id": CLIENT_ID}
)


def access_token(officer_code: str, key=SIGNING_KEY) -> str:
    claims = {
        "iss": cognito_issuer(SETTINGS),
        "token_use": "access",
        "client_id": CLIENT_ID,
        "username": officer_code,
        "exp": int(time.time()) + 300,
    }
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture(scope="module")
def mcp_url():
    """The MCP server on a free local port, the way the ECS container runs it."""

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    server = uvicorn.Server(
        uvicorn.Config(mcp_server.mcp.streamable_http_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)

    yield f"http://127.0.0.1:{port}/mcp"

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def seeded(db: Session, monkeypatch: pytest.MonkeyPatch) -> Session:
    seed_extraction(db)

    @contextmanager
    def session_scope():
        yield db

    keys = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=SIGNING_KEY.public_key()))
    monkeypatch.setattr("dosimeter.api.identity._signing_keys", lambda issuer: keys)
    monkeypatch.setattr(mcp_server, "session_scope", session_scope)
    monkeypatch.setattr(mcp_server, "get_settings", lambda: SETTINGS)
    monkeypatch.setattr(mcp_server, "embedder", lambda text: embedding(1.0))
    return db


def transport(url: str, token: str) -> GatewayTransport:
    return GatewayTransport(url, token_provider=lambda: token)


def test_an_entitled_officer_reads_the_extraction_over_mcp(mcp_url: str, seeded: Session) -> None:
    response = transport(mcp_url, access_token("OFF-101")).get(f"/v1/exposures/{EXPOSURE}/extraction")

    assert response.status == 200
    assert response.payload["exposure_id"] == EXPOSURE
    assert response.payload["low_confidence_field_keys"] == ["Shallow Dose Equivalent"]


def test_the_entitlement_check_runs_against_the_token_officer(mcp_url: str, seeded: Session) -> None:
    response = transport(mcp_url, access_token("OFF-104")).get(f"/v1/exposures/{EXPOSURE}/extraction")

    assert response.status == 403
    assert response.payload["reason_code"] == "no_grants"
    assert response.payload["officer_code"] == "OFF-104"


def test_a_token_the_user_pool_did_not_sign_is_refused(mcp_url: str, seeded: Session) -> None:
    forged = access_token("OFF-101", key=rsa.generate_private_key(public_exponent=65537, key_size=2048))

    response = transport(mcp_url, forged).get(f"/v1/exposures/{EXPOSURE}/extraction")

    assert response.status == 403
    assert response.payload["reason_code"] == "no_verified_identity"


def test_the_equipment_worker_search_succeeds_over_mcp(mcp_url: str, seeded: Session) -> None:
    toolset = ApiToolset(transport=transport(mcp_url, access_token("OFF-101")))
    dispatcher = ToolDispatcher(
        registry=build_registry(toolset.tools()),
        ledger=SessionLedger(bounds=Bounds()),
        subject=Subject(session_id="session-1", officer_id=1, officer_code="OFF-101", exposure_id=EXPOSURE),
    )

    found = dispatcher.invoke("find_similar_exposures", {"query_text": "source would not retract", "limit": 2})

    assert found.ok
    assert found.value["candidates"][0]["exposure_id"] == "hist-0001"
    assert toolset.capabilities_lost() == []


def test_a_denial_over_mcp_reaches_the_dispatcher_as_a_denial(mcp_url: str, seeded: Session) -> None:
    toolset = ApiToolset(transport=transport(mcp_url, access_token("OFF-104")))
    dispatcher = ToolDispatcher(
        registry=build_registry(toolset.tools()),
        ledger=SessionLedger(bounds=Bounds()),
        subject=Subject(session_id="session-1", officer_id=4, officer_code="OFF-104", exposure_id=EXPOSURE),
    )

    response = dispatcher.invoke("get_exposure_extraction", {})

    assert response.error.reason_code == ToolErrorCode.DENIED
    assert response.error.detail["api_reason_code"] == "no_grants"
