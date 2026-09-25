"""
A judged run: the judge over every cited claim in a dossier, plus the two
record checks, written to a dated folder with the commit it ran against.

    python -m dosimeter.evaluation.judged_run judged-1 --officer OFF-101 EXP-2026-0412
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dosimeter.config.settings import Settings, get_settings
from dosimeter.errors import DosimeterError
from dosimeter.evaluation.judge import GroundednessJudge, JudgedClaim
from dosimeter.evaluation.record_checks import CheckResult, run_checks
from dosimeter.logging_config import configure_logging, get_logger
from dosimeter.repository import Session, queries

EVALS_ROOT = Path("evals/runs")

_LOGGER = get_logger(__name__)


class JudgedRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    run_on: date
    git_sha: str
    judge_model_id: str
    claims: list[JudgedClaim] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for claim in self.claims:
            counts[claim.verdict.value] = counts.get(claim.verdict.value, 0) + 1
        return counts


def git_sha() -> str:
    git = shutil.which("git")
    if git is None:
        return "unknown"

    try:
        return subprocess.run(  # noqa: S603 - a fixed command on a resolved path
            [git, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def claims_from_dossier(payload: dict) -> list[tuple[str, str, str]]:
    """Claim text, chunk id and chunk text, for everything the dossier cites."""

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
    judge: GroundednessJudge,
) -> tuple[list[JudgedClaim], list[CheckResult]]:
    dossier = queries.latest_dossier(session, exposure_id)
    if dossier is None:
        raise DosimeterError("no dossier to judge", exposure_id=exposure_id)

    claims = [
        judge.judge(claim, chunk_id, chunk_text)
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

    summary = folder / "summary.md"
    lines = [
        f"# Judged run: {results.label}",
        "",
        f"- date: {results.run_on.isoformat()}",
        f"- commit: {results.git_sha}",
        f"- judge model: {results.judge_model_id}",
        "",
        "## Verdicts",
        *[f"- {name}: {count}" for name, count in sorted(results.summary().items())],
        "",
        "## Record checks",
        *[
            f"- {check.name}: {'pass' if check.passed else 'fail'} - {check.detail}"
            for check in results.checks
        ],
    ]
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_judged(
    session: Session,
    label: str,
    exposure_ids: Sequence[str],
    settings: Settings | None = None,
    judge: GroundednessJudge | None = None,
    root: Path = EVALS_ROOT,
) -> JudgedRun:
    resolved = settings or get_settings()
    evaluator = judge or GroundednessJudge(settings=resolved)

    results = JudgedRun(
        label=label,
        run_on=date.today(),
        git_sha=git_sha(),
        judge_model_id=resolved.model_for("judge"),
    )

    for exposure_id in exposure_ids:
        claims, checks = judge_exposure(session, exposure_id, evaluator)
        results.claims.extend(claims)
        results.checks.extend(checks)

    write_results(results, root)
    _LOGGER.info("judged_run.written", extra={"label": label, "summary": results.summary()})
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
        _LOGGER.error("judged_run.failed", extra={"detail": str(error)})
        return 1

    _LOGGER.info("judged_run.done", extra={"claims": len(results.claims)})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
