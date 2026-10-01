"""IAM database authentication: every new connection gets a freshly signed token."""

from unittest.mock import patch

from dosimeter.aws.aws import rds_auth_token
from dosimeter.config.settings import DatabaseSettings
from dosimeter.repository.connection import conn_string, rds_token_provider

RDS = DatabaseSettings(
    _env_file=None,
    host="dosimeter.abc123.us-east-1.rds.amazonaws.com",
    port=5432,
    name="dosimeter",
    user="dosimeter_app",
    use_iam_auth=True,
    sslmode="require",
)


def test_the_token_is_signed_for_the_configured_host_port_and_user() -> None:
    with patch("dosimeter.aws.aws.get_client") as get_client:
        get_client.return_value.generate_db_auth_token.return_value = "signed-token"

        token = rds_auth_token(RDS)

    assert token == "signed-token"
    get_client.assert_called_once_with("rds")
    get_client.return_value.generate_db_auth_token.assert_called_once_with(
        DBHostname="dosimeter.abc123.us-east-1.rds.amazonaws.com",
        Port=5432,
        DBUsername="dosimeter_app",
    )


def test_iam_auth_needs_no_password_and_uses_the_token() -> None:
    with patch("dosimeter.repository.connection.rds_auth_token", return_value="signed-token"):
        url = conn_string(RDS)

    assert "dosimeter_app:signed-token@" in url
    assert "sslmode=require" in url


def test_each_connection_asks_for_a_new_token() -> None:
    tokens = iter(["first-token", "second-token"])

    with patch("dosimeter.repository.connection.rds_auth_token", side_effect=lambda _: next(tokens)):
        provider = rds_token_provider(RDS)

        assert provider() == "first-token"
        assert provider() == "second-token"
