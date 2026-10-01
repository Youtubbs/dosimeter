""" the Dosimeter workflow on AgentCore Runtime. POST /invocations runs one assess turn, GET /ping is the health check """

from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from dosimeter.config.settings import get_settings
from dosimeter.errors import DosimeterError
from dosimeter.graph.checkpointer import setup_checkpointer
from dosimeter.harness.assess import run_assess
from dosimeter.logging_config import configure_logging, correlation_scope
from dosimeter.models.bedrock import embed_text
from dosimeter.repository.connection import session_scope
from dosimeter.repository.migrate import migrate_up
from dosimeter.repository.seeds import apply_seeds

app = BedrockAgentCoreApp()
log = app.logger


# a plain def on purpose. the SDK runs it on a worker thread, where the Gateway
# transport is free to start its own event loop
@app.entrypoint
def invoke(payload: dict[str, Any], context) -> dict[str, Any]:
    """ handle POST /invocations
            expect body to be: {"command": "assess", "exposure_id": "...", "officer_code": "..."}
            or {"command": "migrate"}, since RDS is only reachable from inside the VPC
    """

    # the AgentCore SDK maps the header 'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id' to context's session_id
    session_id = getattr(context, "session_id", None)
    command = payload.get("command")

    try:
        if command == "assess":
            return assess(payload, session_id)
        if command == "migrate":
            return migrate()
    except DosimeterError as error:
        log.error("[session=%s] %s failed: %s", session_id, command, error)
        return {"error": str(error)}

    return {"error": "Expected command 'assess' or 'migrate'."}


def assess(payload: dict[str, Any], session_id: str | None) -> dict[str, Any]:
    exposure_id = payload.get("exposure_id")
    officer_code = payload.get("officer_code")
    if not isinstance(exposure_id, str) or not isinstance(officer_code, str):
        return {"error": "Expected string fields 'exposure_id' and 'officer_code'."}

    # the turn reads and writes Postgres exactly as it does in the CLI
    with correlation_scope(), session_scope() as session:
        result = run_assess(
            session=session,
            exposure_id=exposure_id,
            officer_code=officer_code,
            settings=get_settings(),
            runtime_arn=payload.get("runtime_arn"),
            runtime_session_id=session_id,
            access_token=payload.get("access_token"),
        )

    log.info("[session=%s] assessed %s: %s", session_id, exposure_id, result.outcome)

    # formatting the HTTP response
    return result.model_dump(mode="json")


def migrate() -> dict[str, Any]:
    """ the schema, the seed rows and the checkpoint tables. each step is safe to repeat """

    with session_scope() as session:
        applied = migrate_up(session)
        seeded = apply_seeds(session, embed=embed_text)
    setup_checkpointer()

    log.info("migrated %s, seeded %s", applied or "nothing new", seeded)
    return {"applied": applied, "seeded": seeded}


if __name__ == "__main__":

    configure_logging(get_settings().log_level)

    # what starts up the server on port 8080
    app.run()
