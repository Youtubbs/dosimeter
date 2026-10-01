"""The token an outside MCP client uses to call the read tools Gateway as one officer."""

import pytest
from botocore.exceptions import ClientError

from dosimeter.aws import officer_token

SETTINGS = {
    "AWS_REGION": "us-east-1",
    "BEDROCK_MODEL_ID": "text-model-id",
    "BEDROCK_EMBED_MODEL_ID": "embedding-model-id",
    "BEDROCK_KB_ID": "kb-000000",
    "DOSIMETER_GUARDRAIL_ID": "gr-000000",
    "AWS_CORPUS_BUCKET_NAME": "dosimeter-corpus",
    "AWS_PACKET_BUCKET_NAME": "dosimeter-packets",
}


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    for name, value in SETTINGS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("DOSIMETER_IDENTITY_CLIENT_ID", "client-123")
    monkeypatch.setenv("DOSIMETER_IDENTITY_PASSWORD", "demo-password")


def test_it_prints_the_token_for_the_named_officer(configured, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    signed_in = []
    monkeypatch.setattr(
        officer_token,
        "cognito_access_token",
        lambda officer, password, client_id: signed_in.append((officer, password, client_id)) or "token-102",
    )

    assert officer_token.main(["OFF-102"]) == 0
    assert capsys.readouterr().out == "token-102\n"
    assert signed_in == [("OFF-102", "demo-password", "client-123")]

    assert officer_token.main(["OFF-102", "--header"]) == 0
    assert capsys.readouterr().out == "Authorization: Bearer token-102\n"


def test_it_needs_the_identity_settings(configured, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.delenv("DOSIMETER_IDENTITY_PASSWORD")

    assert officer_token.main(["OFF-102"]) == 2
    assert "DOSIMETER_IDENTITY_PASSWORD" in capsys.readouterr().err


def test_a_refused_sign_in_is_reported_not_raised(configured, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    def refused(*_args):
        raise ClientError({"Error": {"Code": "NotAuthorizedException", "Message": "Incorrect"}}, "InitiateAuth")

    monkeypatch.setattr(officer_token, "cognito_access_token", refused)

    assert officer_token.main(["OFF-102"]) == 1
    assert "sign-in failed" in capsys.readouterr().err
