""" the Dosimeter workflow on AgentCore Runtime. POST /invocations runs one assess turn, GET /ping is the health check """

from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from dosimeter.config.settings import get_settings
from dosimeter.errors import DosimeterError
from dosimeter.graph.checkpointer import setup_checkpointer
from dosimeter.harness.assess import run_assess
from dosimeter.logging_config import configure_logging, correlation_scope
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
            or {"command": "migrate"} or {"command": "seed"}
    """

    command = payload.get("command")

    # RDS is private, so the schema and the demo seeds are applied from inside the VPC, here
    if command == "migrate":
        return _database_step("migrate", _migrate)
    if command == "seed":
        return _database_step("seed", _seed)

    if command != "assess":
        return {"error": "Expected command 'assess', 'migrate' or 'seed'."}

    exposure_id = payload.get("exposure_id")
    officer_code = payload.get("officer_code")
    if not isinstance(exposure_id, str) or not isinstance(officer_code, str):
        return {"error": "Expected string fields 'exposure_id' and 'officer_code'."}

    # the AgentCore SDK maps the header 'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id' to context's session_id
    session_id = getattr(context, "session_id", None)

    # the turn reads and writes Postgres exactly as it does in the CLI
    try:
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
    except DosimeterError as error:
        log.error("[session=%s] assess failed: %s", session_id, error)
        return {"error": str(error)}

    log.info("[session=%s] assessed %s: %s", session_id, exposure_id, result.outcome)

    # formatting the HTTP response
    return result.model_dump(mode="json")


def _migrate() -> dict[str, Any]:
    with session_scope() as session:
        applied = migrate_up(session)
    setup_checkpointer()
    return {"applied": applied}


def _seed() -> dict[str, Any]:
    with session_scope() as session:
        return {"seeded": apply_seeds(session)}


def _database_step(name: str, step) -> dict[str, Any]:
    try:
        result = step()
    except DosimeterError as error:
        log.error("%s failed: %s", name, error)
        return {"error": str(error)}

    log.info("%s done: %s", name, result)
    return result


if __name__ == "__main__":

    configure_logging(get_settings().log_level)

    # what starts up the server on port 8080
    app.run()
