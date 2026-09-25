"""
The run record writer. One row per turn, plus a child row for everything the
turn did, so trace and the evaluators read facts rather than prose.

Everything written here goes through the redactor first. No worker name and no
dose history reaches a run record.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from dosimeter.logging_config import get_correlation_id, get_logger
from dosimeter.redaction import redact_value
from dosimeter.repository import Session, queries
from dosimeter.repository.models import (
    EscalationTrigger,
    GuardrailEvent,
    ModelCall,
    Retrieval,
    ReviewerVerdictRecord,
    RuleInvocation,
    RunRecord,
    ToolInvocation,
    WorkerDispatch,
)

_LOGGER = get_logger(__name__)


def sha256_of(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _clean(payload: Any) -> Any:
    return redact_value(payload).value


@dataclass
class RunRecorder:
    """
    Collects what a turn did and writes it. Nothing is buffered in a way that
    survives the process: a turn that dies mid-way still leaves its header row.
    """

    session: Session
    exposure_id: str | None = None
    officer_id: int | None = None
    session_id: UUID | None = None
    command: str = "assess"
    turn_kind: str = "assess"
    run_id: UUID = field(default_factory=uuid4)
    token_totals: dict[str, int] = field(default_factory=dict)
    _started: bool = False

    def start(self) -> UUID:
        """Write the header row so children have something to hang from."""

        queries.insert_run_record(
            self.session,
            RunRecord(
                id=self.run_id,
                correlation_id=get_correlation_id(),
                command=self.command,
                turn_kind=self.turn_kind,
                exposure_id=self.exposure_id,
                officer_id=self.officer_id,
                session_id=self.session_id,
            ),
        )
        self.session.commit()
        self._started = True
        return self.run_id

    def dispatched(
        self,
        worker: str,
        reason: str,
        iteration: int = 1,
        redispatch_trigger: str | None = None,
    ) -> None:
        queries.add_worker_dispatch(
            self.session,
            WorkerDispatch(
                run_id=self.run_id,
                worker=worker,
                reason=_clean(reason),
                iteration=iteration,
                redispatch_trigger=redispatch_trigger,
            ),
        )

    def tool_called(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any] | None,
        outcome: str,
        worker: str | None = None,
        duration_ms: float | None = None,
        argument_sha256: str | None = None,
    ) -> None:
        queries.add_tool_invocation(
            self.session,
            ToolInvocation(
                run_id=self.run_id,
                tool_name=tool_name,
                argument_sha256=argument_sha256 or sha256_of(arguments),
                arguments=_clean(arguments),
                result=_clean(result) if result is not None else None,
                outcome=outcome,
                worker=worker,
                duration_ms=duration_ms,
            ),
        )

    def rule_invoked(
        self,
        rule_id: str,
        outcome: str,
        inputs: dict[str, Any],
        result: dict[str, Any] | None = None,
        threshold_named: str | None = None,
        dose_quantity: str | None = None,
        path: str | None = None,
    ) -> None:
        queries.add_rule_invocation(
            self.session,
            RuleInvocation(
                run_id=self.run_id,
                rule_id=rule_id,
                outcome=outcome,
                inputs=_clean(inputs),
                result=_clean(result or {}),
                threshold_named=threshold_named,
                dose_quantity=dose_quantity,
                path=path,
            ),
        )

    def retrieved(
        self,
        query_text: str,
        chunk_ids: list[str],
        scores: list[float],
        statuses: list[str],
        status_filter: str | None = None,
    ) -> None:
        queries.add_retrieval(
            self.session,
            Retrieval(
                run_id=self.run_id,
                query_sha256=sha256_of(query_text),
                query_text=_clean(query_text),
                chunk_ids=chunk_ids,
                scores=scores,
                statuses=statuses,
                status_filter=status_filter,
            ),
        )

    def model_called(
        self,
        model_id: str,
        role: str,
        input_tokens: int,
        output_tokens: int,
        agent: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        queries.add_model_call(
            self.session,
            ModelCall(
                run_id=self.run_id,
                model_id=model_id,
                role=role,
                agent=agent,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
            ),
        )

        key = agent or role
        self.token_totals[key] = self.token_totals.get(key, 0) + input_tokens + output_tokens

    def reviewer_verdict(
        self,
        iteration: int,
        worker: str,
        verdict: str,
        objections: list[dict[str, Any]] | None = None,
    ) -> None:
        queries.add_reviewer_verdict(
            self.session,
            ReviewerVerdictRecord(
                run_id=self.run_id,
                iteration=iteration,
                worker=worker,
                verdict=verdict,
                objections=_clean(objections or []),
            ),
        )

    def trigger_evaluated(self, name: str, fired: bool, detail: str | None = None) -> None:
        queries.add_escalation_trigger(
            self.session,
            EscalationTrigger(
                run_id=self.run_id,
                trigger_name=name,
                evaluated=True,
                fired=fired,
                detail=_clean(detail) if detail else None,
            ),
        )

    def guardrail_event(
        self,
        stage: str,
        action: str,
        guardrail_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        queries.add_guardrail_event(
            self.session,
            GuardrailEvent(
                run_id=self.run_id,
                stage=stage,
                action=action,
                guardrail_id=guardrail_id,
                detail=_clean(detail or {}),
            ),
        )
        _LOGGER.info("guardrail.event", extra={"stage": stage, "action": action})

    def finish(self, outcome: str) -> None:
        """Close the turn and store the per-agent token totals."""

        queries.set_token_totals(self.session, self.run_id, self.token_totals)
        queries.finish_run_record(self.session, self.run_id, outcome)
        self.session.commit()

    def correct(self, outcome: str, command: str | None = None) -> UUID:
        """
        A correction is a new record pointing at this one. Run records are never
        edited in place.
        """

        correction = RunRecord(
            id=uuid4(),
            correlation_id=get_correlation_id(),
            command=command or self.command,
            turn_kind=self.turn_kind,
            exposure_id=self.exposure_id,
            officer_id=self.officer_id,
            session_id=self.session_id,
            outcome=outcome,
            token_totals=dict(self.token_totals),
        )
        queries.correct_run_record(self.session, correction, self.run_id)
        self.session.commit()
        return correction.id
