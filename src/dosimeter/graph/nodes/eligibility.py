"""The eligibility check at the end of every turn."""

from typing import Any

from dosimeter.config.settings import NearBoundaryMargins
from dosimeter.graph.state import GraphState
from dosimeter.guardrails.readiness import ReadinessInput, RequestKind, evaluate_readiness
from dosimeter.harness.escalation import TriggerSignals, evaluate


def route_on_readiness(state: GraphState) -> str:
    """A dose field the officer cannot trust stops the turn before any worker is dispatched."""

    decision = evaluate_readiness(
        ReadinessInput(
            request_kind=RequestKind.ASSESS,
            normalized_record_present=True,
            low_confidence_fields=tuple(state.get("low_confidence_fields") or ()),
            missing_required_fields=tuple(state.get("missing_dose_fields") or ()),
        )
    )
    return "coordinator" if decision.may_dispatch_workers else "eligibility_check"


def rule_results(state: GraphState) -> dict[str, dict[str, Any]]:
    """The last result of each rule this turn, read from the recorded tool calls."""

    results: dict[str, dict[str, Any]] = {}
    for invocation in state.get("rule_invocations") or []:
        if invocation.get("tool") == "evaluate_rule" and invocation.get("result"):
            result = invocation["result"]["result"]
            results[result["rule_id"]] = result
    return results


def _amount(value: Any) -> tuple[float, str] | None:
    # a dose is {"value", "unit"}; an intake is a bare multiple of the ALI
    if isinstance(value, dict) and "value" in value:
        return float(value["value"]), str(value.get("unit") or "ali")
    if isinstance(value, (int, float)):
        return float(value), "ali"
    return None


def _measured(inputs: dict[str, Any], quantity: str) -> tuple[float, str] | None:
    name = "intake" if quantity.startswith("intake") else quantity
    return _amount(inputs.get(name) or inputs.get(f"annual_{name}"))


def dose_checks(
    results: dict[str, dict[str, Any]], margins: NearBoundaryMargins
) -> tuple[list[str], list[str]]:
    """Which doses sit within a margin of a rule's limit, and which reach an annual limit (R3)."""

    near: list[str] = []
    annual: list[str] = []

    for rule_id, result in results.items():
        inputs = result.get("inputs_used") or {}

        for quantity, threshold in (result.get("threshold") or {}).items():
            limit, measured = _amount(threshold), _measured(inputs, quantity)
            if limit is None or measured is None or limit[1] != measured[1]:
                continue

            name = "intake" if quantity.startswith("intake") else quantity
            margin = getattr(margins, f"{rule_id.lower()}_{name}_{limit[1].lower()}", None)

            if margin is not None and abs(measured[0] - limit[0]) <= margin:
                near.append(f"{rule_id} {name}")
            if rule_id == "R3" and measured[0] >= limit[0]:
                annual.append(f"{name} {measured[0]} {limit[1]}")

    return near, annual


def signals_from_state(state: GraphState, margins: NearBoundaryMargins | None = None) -> TriggerSignals:
    """Read the turn's own record out of graph state. No model opinion here."""

    verdicts = state.get("reviewer_verdicts") or []
    guardrail_events = state.get("guardrail_events") or []

    prompt_attack_fired = any(
        event.trigger == "prompt_attack_filter_fired" for event in guardrail_events
    )

    unresolved_citations = [
        event.detail
        for event in guardrail_events
        if event.trigger == "proposed_source_determination"
    ]

    # approved means approved on the first pass
    latest = {verdict.worker: verdict.verdict for verdict in verdicts}
    iterations = state.get("reviewer_iterations", 0)

    results = rule_results(state)
    near, annual = dose_checks(results, margins or NearBoundaryMargins())

    return TriggerSignals(
        fields_below_floor=[
            *(state.get("low_confidence_fields") or []),
            *(f"{field} (not readable)" for field in state.get("missing_dose_fields") or []),
        ],
        insufficient_data_rules=sorted(
            rule_id for rule_id, result in results.items() if result["outcome"] == "insufficient_data"
        ),
        near_boundary_rules=near,
        reviewer_iterations=iterations,
        reviewer_approved=bool(latest) and iterations <= 1 and all(v == "approved" for v in latest.values()),
        unresolved_citations=unresolved_citations,
        retrieval_below_threshold=any(
            entry.get("found") is False for entry in state.get("retrieval_log") or []
        ),
        prompt_attack_fired=prompt_attack_fired,
        notification_required_rules=sorted(
            rule_id
            for rule_id, result in results.items()
            if rule_id in {"R1", "R2"} and result["outcome"] == "required"
        ),
        planned_special_exposure_valid=results.get("R4", {}).get("outcome") == "valid",
        doses_at_or_above_annual_limit=annual,
    )


def eligibility_node(state: GraphState) -> dict:
    """
    Decide from deterministic signals whether the dossier stands or goes to a
    person. The harness records the result and queues the dossier.
    """

    escalation = evaluate(signals_from_state(state))

    return {
        "escalation": escalation,
        "outcome": ("escalated" if escalation.escalates else "ready_for_officer"),
    }
