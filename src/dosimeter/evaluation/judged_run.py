"""
A judged run: the judge over every cited claim in a dossier, plus the two
record checks, written to evals/runs/<label>/results.json. Commit the file;
the next judged run is compared against it.

    python -m dosimeter.evaluation.judged_run judged-1 EXP-2026-0412
"""

import argparse
import logging
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from uuid import UUID

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, ConfigDict, Field

from dosimeter.config.settings import Settings, get_settings
from dosimeter.errors import DosimeterError
from dosimeter.evaluation.judge import JUDGE_ROLE, JudgedClaim, judge_claim
from dosimeter.evaluation.record_checks import CheckResult, run_checks
from dosimeter.logging_config import configure_logging
from dosimeter.repository import Session, queries

EVALS_ROOT = Path("evals/runs")

logger = logging.getLogger(__name__)


class JudgedRun(BaseModel):
    """Everything one judged run found."""

    model_config = ConfigDict(extra="forbid")

    label: str
    run_on: date
    judge_model_id: str
    claims: list[JudgedClaim] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)

    def summary(self) -> dict[str, int]:
        """How many claims got each verdict."""

        counts: dict[str, int] = {}
        for claim in self.claims:
            counts[claim.verdict.value] = counts.get(claim.verdict.value, 0) + 1
        return counts


def claims_from_dossier(payload: dict) -> list[tuple[str, str, str]]:
    """Claim text, cited id and cited text, for everything the dossier cites."""

    found: list[tuple[str, str, str]] = []
    for source in payload.get("sources", []) or []:
        claim = source.get("claim") or payload.get("outcome") or ""
        chunk_id = source.get("chunk_id", "")
        chunk_text = source.get("chunk_text", "")
        if claim and chunk_id and chunk_text:
            found.append((claim, chunk_id, chunk_text))
    return found


def judge_exposure(
    session: Session,
    exposure_id: str,
    settings: Settings,
    model: BaseChatModel | None = None,
) -> tuple[list[JudgedClaim], list[CheckResult]]:
    dossier = queries.latest_dossier(session, exposure_id)
    if dossier is None:
        raise DosimeterError("no dossier to judge", exposure_id=exposure_id)

    claims = [
        judge_claim(claim, chunk_id, chunk_text, settings, model=model)
        for claim, chunk_id, chunk_text in claims_from_dossier(dossier.payload)
    ]

    claimed_rules = [
        item.get("rule_id", "")
        for item in dossier.payload.get("rule_invocations", []) or []
        if item.get("rule_id")
    ]
    checks = run_checks(session, UUID(str(dossier.run_id)), claimed_rules)
    return claims, checks


def write_results(results: JudgedRun, root: Path = EVALS_ROOT) -> Path:
    folder = root / results.label
    folder.mkdir(parents=True, exist_ok=True)

    path = folder / "results.json"
    path.write_text(results.model_dump_json(indent=2), encoding="utf-8")
    return path


def run_judged(
    session: Session,
    label: str,
    exposure_ids: Sequence[str],
    settings: Settings | None = None,
    model: BaseChatModel | None = None,
    root: Path = EVALS_ROOT,
) -> JudgedRun:
    resolved = settings or get_settings()

    results = JudgedRun(
        label=label,
        run_on=date.today(),
        judge_model_id=resolved.model_for(JUDGE_ROLE),
    )

    for exposure_id in exposure_ids:
        claims, checks = judge_exposure(session, exposure_id, resolved, model=model)
        results.claims.extend(claims)
        results.checks.extend(checks)

    write_results(results, root)
    logger.info("judged_run.written", extra={"label": label, "summary": results.summary()})
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dosimeter-judged-run")
    parser.add_argument("label", help="the folder under evals/runs, for example judged-1")
    parser.add_argument("exposure_ids", nargs="+")
    args = parser.parse_args(argv)

    configure_logging()

    from dosimeter.repository.connection import session_scope

    try:
        with session_scope() as session:
            results = run_judged(session, args.label, args.exposure_ids)
    except DosimeterError as error:
        logger.error("judged_run.failed", extra={"detail": str(error)})
        return 1

    logger.info("judged_run.done", extra={"claims": len(results.claims)})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
