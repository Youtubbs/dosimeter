"""The workflow on AgentCore Runtime: the entrypoint, the contract it serves, and the CLI client."""

import io
import json
import uuid
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from dosimeter.aws import aws
from dosimeter.cli.main import main
from dosimeter.config.settings import Settings
from dosimeter.errors import ConfigurationError, ExternalServiceError, GateError
from dosimeter.harness.assess import AssessResult
from dosimeter.harness.eligibility import EligibilityResult
from dosimeter.harness.escalation import EscalationOutcome
from dosimeter.runtime import client
from dosimeter.runtime import main as runtime_main
from dosimeter.runtime.client import SESSION_HEADER, run_assess_on_runtime, runtime_session_id

# nothing listens here, so every call is refused straight away
DEAD_RUNTIME = "http://127.0.0.1:1"
RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/DosimeterWorkflow-abc"


def settings_for_tests(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        bedrock_model_id="text-model-id",
        bedrock_embed_model_id="embedding-model-id",
        knowledge_base_id="kb",
        guardrail_id="gr",
        corpus_bucket="corpus",
        packet_bucket="packets",
        **overrides,
    )


def assess_result(exposure_id: str = "EXP-2026-0412") -> AssessResult:
    return AssessResult(
        exposure_id=exposure_id,
        run_id=uuid.uuid4(),
        outcome="drafted",
        dossier_id=7,
        duration_seconds=1.5,
        eligibility=EligibilityResult(outcome=EscalationOutcome()),
    )


@pytest.fixture
def fake_turn(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Stand in for the database and the graph, and keep what run_assess was called with."""

    calls: list[dict] = []

    @contextmanager
    def no_database():
        yield object()

    def fake_run_assess(**kwargs) -> AssessResult:
        calls.append(kwargs)
        return assess_result(kwargs["exposure_id"])

    monkeypatch.setattr(runtime_main, "session_scope", no_database)
    monkeypatch.setattr(runtime_main, "get_settings", settings_for_tests)
    monkeypatch.setattr(runtime_main, "run_assess", fake_run_assess)
    return calls


class FakeAgentCore:
    def __init__(self, body: dict) -> None:
        self.body = body
        self.calls: list[dict] = []

    def invoke_agent_runtime(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {"response": io.BytesIO(json.dumps(self.body).encode())}


def test_only_the_assess_command_runs_on_the_runtime(fake_turn: list[dict]) -> None:
    response = runtime_main.invoke({"command": "ask"}, SimpleNamespace(session_id="s"))

    assert "error" in response
    assert fake_turn == []


def test_the_entrypoint_rejects_a_payload_without_string_ids(fake_turn: list[dict]) -> None:
    response = runtime_main.invoke(
        {"command": "assess", "exposure_id": 412, "officer_code": "OFF-101"},
        SimpleNamespace(session_id="s"),
    )

    assert "error" in response
    assert fake_turn == []


def test_the_entrypoint_runs_the_turn_with_where_it_ran(fake_turn: list[dict]) -> None:
    payload = {
        "command": "assess",
        "exposure_id": "EXP-2026-0412",
        "officer_code": "OFF-101",
        "runtime_arn": RUNTIME_ARN,
        "access_token": "officer-token",
    }

    response = runtime_main.invoke(payload, SimpleNamespace(session_id="dosimeter-session"))

    assert AssessResult.model_validate(response).exposure_id == "EXP-2026-0412"
    [call] = fake_turn
    assert call["officer_code"] == "OFF-101"
    assert call["runtime_arn"] == RUNTIME_ARN
    assert call["runtime_session_id"] == "dosimeter-session"
    assert call["access_token"] == "officer-token"


def test_a_failed_turn_comes_back_as_an_error_body(monkeypatch: pytest.MonkeyPatch, fake_turn) -> None:
    def no_such_exposure(**_kwargs):
        raise GateError("no such exposure", exposure_id="EXP-9999-0000")

    monkeypatch.setattr(runtime_main, "run_assess", no_such_exposure)

    response = runtime_main.invoke(
        {"command": "assess", "exposure_id": "EXP-9999-0000", "officer_code": "OFF-101"},
        SimpleNamespace(session_id="s"),
    )

    assert response["error"].startswith("no such exposure")


def test_the_app_serves_the_runtime_contract(fake_turn: list[dict]) -> None:
    session_id = runtime_session_id("OFF-101", "EXP-2026-0412")

    with TestClient(runtime_main.app) as http:
        assert http.get("/ping").json()["status"] == "Healthy"

        response = http.post(
            "/invocations",
            json={"command": "assess", "exposure_id": "EXP-2026-0412", "officer_code": "OFF-101"},
            headers={SESSION_HEADER: session_id},
        )

    assert response.status_code == 200
    assert response.json()["dossier_id"] == 7
    assert fake_turn[0]["runtime_session_id"] == session_id


def test_the_session_id_is_long_enough_and_stable_per_officer_and_exposure() -> None:
    session_id = runtime_session_id("OFF-101", "EXP-2026-0412")

    assert len(session_id) >= 33
    assert session_id == runtime_session_id("OFF-101", "EXP-2026-0412")
    assert session_id != runtime_session_id("OFF-102", "EXP-2026-0412")


def test_the_deployed_runtime_is_invoked_by_arn(monkeypatch: pytest.MonkeyPatch) -> None:
    agentcore = FakeAgentCore(assess_result().model_dump(mode="json"))
    timeouts: list[float | None] = []

    def fake_get_client(service_name: str, read_timeout: float | None = None):
        assert service_name == "bedrock-agentcore"
        timeouts.append(read_timeout)
        return agentcore

    monkeypatch.setattr(aws, "get_client", fake_get_client)
    settings = settings_for_tests(runtime_arn=RUNTIME_ARN)

    result = run_assess_on_runtime(settings, "EXP-2026-0412", "OFF-101")

    assert result.dossier_id == 7
    [call] = agentcore.calls
    assert call["agentRuntimeArn"] == RUNTIME_ARN
    assert call["runtimeSessionId"] == runtime_session_id("OFF-101", "EXP-2026-0412")
    assert json.loads(call["payload"]) == {
        "command": "assess",
        "exposure_id": "EXP-2026-0412",
        "officer_code": "OFF-101",
        "runtime_arn": RUNTIME_ARN,
    }
    # the read waits out a whole turn, not just one model call
    assert timeouts == [settings.bounds.per_turn_wall_clock_seconds + 30]


def test_through_the_gateway_the_officer_token_rides_along(monkeypatch: pytest.MonkeyPatch) -> None:
    agentcore = FakeAgentCore(assess_result().model_dump(mode="json"))
    monkeypatch.setattr(aws, "get_client", lambda *_args, **_kwargs: agentcore)
    monkeypatch.setattr(client, "cognito_access_token", lambda officer, *_: f"token-for-{officer}")
    settings = settings_for_tests(
        runtime_arn=RUNTIME_ARN,
        tool_transport="gateway",
        gateway_url="https://gateway.example/mcp",
        identity_client_id="client",
        identity_password="secret",
    )

    run_assess_on_runtime(settings, "EXP-2026-0412", "OFF-101")

    assert json.loads(agentcore.calls[0]["payload"])["access_token"] == "token-for-OFF-101"


def test_an_error_body_from_the_runtime_is_a_typed_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    agentcore = FakeAgentCore({"error": "no such exposure"})
    monkeypatch.setattr(aws, "get_client", lambda *_args, **_kwargs: agentcore)

    with pytest.raises(ExternalServiceError):
        run_assess_on_runtime(settings_for_tests(runtime_arn=RUNTIME_ARN), "EXP-9999-0000", "OFF-101")


def test_the_stand_in_gets_the_session_header(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = []

    def fake_urlopen(request, timeout):
        sent.append(request)
        return io.BytesIO(json.dumps(assess_result().model_dump(mode="json")).encode())

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)

    run_assess_on_runtime(settings_for_tests(runtime_url="http://localhost:8081/"), "EXP-2026-0412", "OFF-101")

    [request] = sent
    assert request.full_url == "http://localhost:8081/invocations"
    assert request.get_header(SESSION_HEADER.capitalize()) == runtime_session_id("OFF-101", "EXP-2026-0412")


def test_an_unreachable_stand_in_is_a_typed_failure() -> None:
    with pytest.raises(ExternalServiceError):
        run_assess_on_runtime(settings_for_tests(runtime_url=DEAD_RUNTIME), "EXP-2026-0412", "OFF-101")


def test_the_runtime_needs_an_arn_or_a_url() -> None:
    with pytest.raises(ConfigurationError):
        run_assess_on_runtime(settings_for_tests(), "EXP-2026-0412", "OFF-101")

    with pytest.raises(ConfigurationError):
        run_assess_on_runtime(settings_for_tests(runtime_url="file:///etc/passwd"), "EXP-2026-0412", "OFF-101")


def test_the_cli_sends_assess_to_the_runtime_when_asked(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    for name, value in {
        "AWS_REGION": "us-east-1",
        "BEDROCK_MODEL_ID": "text-model-id",
        "BEDROCK_EMBED_MODEL_ID": "embedding-model-id",
        "BEDROCK_KB_ID": "kb-000000",
        "DOSIMETER_GUARDRAIL_ID": "gr-000000",
        "AWS_CORPUS_BUCKET_NAME": "dosimeter-corpus",
        "AWS_PACKET_BUCKET_NAME": "dosimeter-packets",
        "DOSIMETER_DB_HOST": "localhost",
        "DOSIMETER_DB_NAME": "dosimeter",
        "DOSIMETER_DB_USER": "dosimeter_app",
        "DOSIMETER_WORKFLOW": "runtime",
        "DOSIMETER_RUNTIME_URL": "http://localhost:8081",
    }.items():
        monkeypatch.setenv(name, value)

    sent = []
    monkeypatch.setattr(
        client,
        "run_assess_on_runtime",
        lambda settings, exposure_id, officer_code: sent.append(officer_code) or assess_result(exposure_id),
    )

    assert main(["assess", "EXP-2026-0412", "--officer", "OFF-101"]) == 0
    assert sent == ["OFF-101"]
    assert "outcome:   drafted" in capsys.readouterr().out


@pytest.fixture
def fake_database_steps(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stand in for the migration runner, the checkpointer setup and the seeds."""

    steps: list[str] = []

    @contextmanager
    def no_database():
        yield object()

    monkeypatch.setattr(runtime_main, "session_scope", no_database)
    monkeypatch.setattr(runtime_main, "migrate_up", lambda session: steps.append("migrate") or ["0004_runtime_invocation"])
    monkeypatch.setattr(runtime_main, "setup_checkpointer", lambda: steps.append("checkpointer"))
    monkeypatch.setattr(runtime_main, "apply_seeds", lambda session: steps.append("seed") or {"officers": 4})
    return steps


def test_the_runtime_migrates_the_database_from_inside_the_vpc(fake_database_steps: list[str]) -> None:
    response = runtime_main.invoke({"command": "migrate"}, SimpleNamespace(session_id="s"))

    assert response == {"applied": ["0004_runtime_invocation"]}
    assert fake_database_steps == ["migrate", "checkpointer"]


def test_the_runtime_seeds_the_database(fake_database_steps: list[str]) -> None:
    response = runtime_main.invoke({"command": "seed"}, SimpleNamespace(session_id="s"))

    assert response == {"seeded": {"officers": 4}}
    assert fake_database_steps == ["seed"]


def test_a_failed_migration_comes_back_as_an_error_body(monkeypatch: pytest.MonkeyPatch, fake_database_steps) -> None:
    def unreachable(session):
        raise ExternalServiceError("database call failed")

    monkeypatch.setattr(runtime_main, "migrate_up", unreachable)

    response = runtime_main.invoke({"command": "migrate"}, SimpleNamespace(session_id="s"))

    assert response["error"].startswith("database call failed")
    assert "checkpointer" not in fake_database_steps


def runtime_env(monkeypatch: pytest.MonkeyPatch, tmp_path, **extra: str) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DOSIMETER_RUNTIME_ARN", raising=False)
    monkeypatch.delenv("DOSIMETER_RUNTIME_URL", raising=False)
    for name, value in {
        "AWS_REGION": "us-east-1",
        "BEDROCK_MODEL_ID": "text-model-id",
        "BEDROCK_EMBED_MODEL_ID": "embedding-model-id",
        "BEDROCK_KB_ID": "kb-000000",
        "DOSIMETER_GUARDRAIL_ID": "gr-000000",
        "AWS_CORPUS_BUCKET_NAME": "dosimeter-corpus",
        "AWS_PACKET_BUCKET_NAME": "dosimeter-packets",
        **extra,
    }.items():
        monkeypatch.setenv(name, value)


def test_the_migrate_command_goes_to_the_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    runtime_env(monkeypatch, tmp_path, DOSIMETER_RUNTIME_ARN=RUNTIME_ARN)
    agentcore = FakeAgentCore({"applied": []})
    monkeypatch.setattr(aws, "get_client", lambda *_args, **_kwargs: agentcore)

    assert client.main(["migrate"]) == 0

    [call] = agentcore.calls
    assert json.loads(call["payload"])["command"] == "migrate"
    assert len(call["runtimeSessionId"]) >= 33


def test_the_migrate_command_fails_on_an_error_body_or_no_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    runtime_env(monkeypatch, tmp_path)
    assert client.main(["migrate"]) == 1

    runtime_env(monkeypatch, tmp_path, DOSIMETER_RUNTIME_ARN=RUNTIME_ARN)
    monkeypatch.setattr(aws, "get_client", lambda *_args, **_kwargs: FakeAgentCore({"error": "database call failed"}))
    assert client.main(["seed"]) == 1


def test_an_aws_error_from_the_runtime_is_a_typed_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from botocore.exceptions import ClientError

    class Refusing:
        def invoke_agent_runtime(self, **_kwargs):
            raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "InvokeAgentRuntime")

    monkeypatch.setattr(aws, "get_client", lambda *_args, **_kwargs: Refusing())

    with pytest.raises(ExternalServiceError, match="AgentCore Runtime call failed"):
        run_assess_on_runtime(settings_for_tests(runtime_arn=RUNTIME_ARN), "EXP-2026-0412", "OFF-101")
