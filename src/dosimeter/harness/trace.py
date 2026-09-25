"""
Renders a stored run record. Everything printed here was read back from
Postgres, so a trace works in a process that did not run the turn.
"""

from __future__ import annotations

from uuid import UUID

from dosimeter.repository import Session, queries


def _line(label: str, value: object) -> str:
    return f"{label:<22}{value}"


def render_trace(session: Session, exposure_id: str, run_id: UUID | None = None) -> str:
    """The plan, the dispatches, the tool loops, the rules and the totals."""

    row = (
        queries.get_run_record(session, run_id)
        if run_id is not None
        else queries.latest_run_record(session, exposure_id, command="assess")
    )
    if row is None:
        return f"no run record for {exposure_id}"

    header_id = row.id
    detail = queries.run_record_detail(session, header_id)
    lines = [
        f"run record for {exposure_id}",
        _line("run id", header_id),
        _line("correlation id", row.correlation_id),
        _line("command", row.command),
        _line("outcome", row.outcome or "unfinished"),
    ]
    if getattr(row, "corrects_run_id", None):
        lines.append(_line("corrects", row.corrects_run_id))

    lines.append("")
    lines.append("workers dispatched")
    if detail["dispatches"]:
        for item in detail["dispatches"]:
            trigger = f" (re-dispatch: {item.redispatch_trigger})" if item.redispatch_trigger else ""
            lines.append(f"  {item.iteration}. {item.worker}: {item.reason}{trigger}")
    else:
        lines.append("  none")

    lines.append("")
    lines.append("tool calls")
    if detail["tool_invocations"]:
        for item in detail["tool_invocations"]:
            worker = f"{item.worker}: " if item.worker else ""
            lines.append(
                f"  {worker}{item.tool_name} -> {item.outcome}"
                f" ({item.argument_sha256[:12]}, {item.duration_ms} ms)"
            )
    else:
        lines.append("  none")

    lines.append("")
    lines.append("retrievals")
    if detail["retrievals"]:
        for item in detail["retrievals"]:
            pairs = ", ".join(
                f"{chunk} {score:.2f} {status}"
                for chunk, score, status in zip(
                    item.chunk_ids,
                    item.scores,
                    item.statuses or ["unknown"] * len(item.chunk_ids),
                    strict=False,
                )
            )
            filtered = f" [filter: {item.status_filter}]" if item.status_filter else ""
            lines.append(f"  {pairs or 'nothing returned'}{filtered}")
    else:
        lines.append("  none")

    lines.append("")
    lines.append("rules")
    if detail["rule_invocations"]:
        for item in detail["rule_invocations"]:
            quantity = f" on {item.dose_quantity}" if item.dose_quantity else ""
            threshold = f" against {item.threshold_named}" if item.threshold_named else ""
            lines.append(f"  {item.rule_id}: {item.outcome}{quantity}{threshold}")
            lines.append(f"      inputs: {item.inputs}")
    else:
        lines.append("  none")

    lines.append("")
    lines.append("reviewer")
    if detail["reviewer_verdicts"]:
        for item in detail["reviewer_verdicts"]:
            lines.append(f"  iteration {item.iteration} on {item.worker}: {item.verdict}")
            for objection in item.objections or []:
                lines.append(f"      objection: {objection}")
    else:
        lines.append("  none")

    lines.append("")
    lines.append("escalation triggers")
    if detail["escalation_triggers"]:
        for item in detail["escalation_triggers"]:
            lines.append(f"  {item.trigger_name}: {'fired' if item.fired else 'did not fire'}")
    else:
        lines.append("  none evaluated")

    if detail["guardrail_events"]:
        lines.append("")
        lines.append("guardrail events")
        for item in detail["guardrail_events"]:
            lines.append(f"  {item.stage}: {item.action} {item.detail}")

    lines.append("")
    lines.append("model calls")
    if detail["model_calls"]:
        for item in detail["model_calls"]:
            agent = item.agent or item.role
            lines.append(
                f"  {agent} on {item.model_id}: "
                f"{item.input_tokens} in, {item.output_tokens} out, {item.duration_ms} ms"
            )
    else:
        lines.append("  none")

    totals = row.token_totals or {}
    lines.append("")
    lines.append("token totals per agent")
    if totals:
        lines.extend(f"  {agent}: {count}" for agent, count in sorted(totals.items()))
    else:
        lines.append("  none recorded")

    if row.finished_at and row.started_at:
        elapsed = (row.finished_at - row.started_at).total_seconds()
        lines.append("")
        lines.append(_line("wall clock", f"{elapsed:.2f} s"))

    return "\n".join(lines)
