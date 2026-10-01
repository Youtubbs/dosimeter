""" print a Cognito access token for one officer, so an outside MCP client
    can call the read tools Gateway as that officer

        python -m dosimeter.aws.officer_token OFF-102
"""

import argparse
import sys
from collections.abc import Sequence

from botocore.exceptions import BotoCoreError, ClientError

from dosimeter.aws.aws import cognito_access_token
from dosimeter.config.settings import load_settings
from dosimeter.errors import ConfigurationError


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dosimeter-officer-token")
    parser.add_argument("officer_code", help="the Cognito user to sign in as, for example OFF-102")
    parser.add_argument("--header", action="store_true", help="print the whole Authorization header")
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
    except ConfigurationError as error:
        sys.stderr.write(f"{error}\n")
        return 2

    if not (settings.identity_client_id and settings.identity_password):
        sys.stderr.write("set DOSIMETER_IDENTITY_CLIENT_ID and DOSIMETER_IDENTITY_PASSWORD in .env\n")
        return 2

    try:
        token = cognito_access_token(
            args.officer_code,
            settings.identity_password.get_secret_value(),
            settings.identity_client_id,
        )
    except (BotoCoreError, ClientError) as error:
        sys.stderr.write(f"sign-in failed: {error}\n")
        return 1

    sys.stdout.write((f"Authorization: Bearer {token}" if args.header else token) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
