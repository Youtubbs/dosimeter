"""Golden evaluation runner."""

from dataclasses import dataclass, field
from uuid import uuid4

from dosimeter.config.settings import Settings
from dosimeter.guardrails.readiness import (
    ReadinessInput,
    RequestKind,
    evaluate_readiness,
)
from dosimeter.harness.assess import run_assess
from dosimeter.harness.escalation import TriggerSignals, evaluate as evaluate_escalation
from dosimeter.repository import Session
from dosimeter.tools.rules import evaluate_rule
from dosimeter.retrieval.retriever import get_retriever
from evals.golden.loader import load_golden_cases
from evals.golden.models import (
    EscalationExecution,
    GoldenCase,
    ReadinessExecution,
    RetrievalExecution,
    RuleExecution,
)


@dataclass
class GoldenResult:
    """Result from evaluating one golden case."""

    case_id: str
    passed: bool
    expected_outcome: str
    actual_outcome: str | None = None
    failures: list[str] = field(default_factory=list)


def compare_outcome(
    case_id: str,
    expected: str,
    actual: str | None,
) -> GoldenResult:
    """Compare an expected golden outcome with the observed outcome."""

    failures: list[str] = []

    if expected != actual:
        failures.append(f"expected {expected}, got {actual}")

    return GoldenResult(
        case_id=case_id,
        passed=not failures,
        expected_outcome=expected,
        actual_outcome=actual,
        failures=failures,
    )


def run_rule_case(
    case: GoldenCase,
    execution: RuleExecution,
) -> GoldenResult:
    """Execute a case through the authoritative deterministic rule adapter."""

    invocation = evaluate_rule(
        {
            "rule_id": execution.rule_id,
            "inputs": execution.inputs,
        }
    )

    actual = invocation.result.outcome.value

    expected = case.expected_outcome
    if case.threshold is not None:
        expected = case.threshold.expected_rule_outcome

    result = compare_outcome(
        case.id,
        expected,
        actual,
    )

    if invocation.rule_id != execution.rule_id:
        result.failures.append(f"expected rule {execution.rule_id}, got {invocation.rule_id}")

    if invocation.path != "tool":
        result.failures.append(f"expected recorded tool invocation, got path {invocation.path}")

    if case.expected_missing_fields:
        actual_missing = set(invocation.result.missing_fields)
        expected_missing = set(case.expected_missing_fields)

        if actual_missing != expected_missing:
            result.failures.append(
                f"expected missing fields {sorted(expected_missing)}, got {sorted(actual_missing)}"
            )

    result.passed = not result.failures
    return result


def run_readiness_case(
    case: GoldenCase,
    execution: ReadinessExecution,
) -> GoldenResult:
    """Execute a case through the deterministic readiness gate."""

    decision = evaluate_readiness(
        ReadinessInput(
            request_kind=RequestKind(execution.request_kind),
            normalized_record_present=execution.normalized_record_present,
            missing_required_fields=execution.missing_required_fields,
            low_confidence_fields=execution.low_confidence_fields,
        )
    )

    if decision.refused:
        actual = "refusal"
    elif decision.human_determination_required and execution.missing_required_fields:
        actual = "insufficient_data"
    elif decision.human_determination_required:
        actual = "human_determination"
    elif decision.may_dispatch_workers:
        actual = "dispatch"
    elif decision.may_answer_from_retrieval:
        actual = "retrieval"
    else:
        actual = "blocked"

    return compare_outcome(
        case.id,
        case.expected_outcome,
        actual,
    )


def run_escalation_case(
    case: GoldenCase,
    execution: EscalationExecution,
) -> GoldenResult:
    """Execute a case through the deterministic escalation evaluator."""

    outcome = evaluate_escalation(
        TriggerSignals(
            fields_below_floor=list(execution.fields_below_floor),
            insufficient_data_rules=list(execution.insufficient_data_rules),
            near_boundary_rules=list(execution.near_boundary_rules),
            reviewer_iterations=execution.reviewer_iterations,
            reviewer_approved=execution.reviewer_approved,
            unresolved_citations=list(execution.unresolved_citations),
            retrieval_below_threshold=execution.retrieval_below_threshold,
            prompt_attack_fired=execution.prompt_attack_fired,
            notification_required_rules=list(execution.notification_required_rules),
            planned_special_exposure_valid=(execution.planned_special_exposure_valid),
            doses_at_or_above_annual_limit=list(execution.doses_at_or_above_annual_limit),
            photo_contradicts_narrative=(execution.photo_contradicts_narrative),
        )
    )

    actual = "escalated" if outcome.escalates else "not_escalated"

    result = compare_outcome(
        case.id,
        case.expected_outcome,
        actual,
    )

    expected_triggers = set(case.expected_triggers)
    actual_triggers = set(outcome.names())

    if expected_triggers != actual_triggers:
        result.failures.append(
            f"expected triggers {sorted(expected_triggers)}, got {sorted(actual_triggers)}"
        )

    result.passed = not result.failures
    return result


def run_retrieval_case(
    case: GoldenCase,
    execution: RetrievalExecution,
) -> GoldenResult:
    """Execute a case through the regulatory knowledge-base retriever."""

    retriever = get_retriever(
        k=execution.k,
        status=execution.status,
    )

    documents = retriever.invoke(case.query)

    failures: list[str] = []

    found = bool(documents)

    if found != execution.expect_found:
        failures.append(f"expected found={execution.expect_found}, got found={found}")

    def source_metadata(document):
        metadata = document.metadata
        nested = metadata.get("source_metadata")

        if isinstance(nested, dict):
            return nested

        return metadata

    actual_sources = {
        (
            str(source_metadata(document).get("doc_id", "")),
            str(source_metadata(document).get("section_path", "")),
        )
        for document in documents
    }

    for expected_source in case.sources:
        source_found = any(
            actual_doc_id == expected_source.document_id
            and (
                expected_source.section == actual_section
                or expected_source.section.startswith(f"{actual_section}(")
            )
            for actual_doc_id, actual_section in actual_sources
        )

        if not source_found:
            failures.append(
                f"missing required source {expected_source.document_id} {expected_source.section}"
            )

    actual_document_ids = {
        str(source_metadata(document).get("doc_id", "")) for document in documents
    }

    for forbidden_source in case.forbidden_sources:
        if forbidden_source in actual_document_ids:
            failures.append(f"retrieved forbidden source {forbidden_source}")

    if execution.status is not None:
        wrong_status_sources = [
            document
            for document in documents
            if source_metadata(document).get("status") != execution.status
        ]

        if wrong_status_sources:
            failures.append(f"retrieval returned sources outside status={execution.status}")

    actual_outcome = "found" if found else "not_found"

    return GoldenResult(
        case_id=case.id,
        passed=not failures,
        expected_outcome=case.expected_outcome,
        actual_outcome=actual_outcome,
        failures=failures,
    )


def run_exposure_case(
    session: Session,
    settings: Settings,
    case: GoldenCase,
    officer_code: str,
) -> GoldenResult:
    """Run a golden case backed by an exposure."""

    if case.exposure_id is None:
        raise ValueError(f"{case.id} does not contain an exposure_id")

    result = run_assess(
        session=session,
        exposure_id=case.exposure_id,
        officer_code=officer_code,
        settings=settings,
        session_id=uuid4(),
    )

    if result.partial is not None:
        print(f"{case.id} stopped early: {result.partial}")

    return compare_outcome(
        case.id,
        case.expected_outcome,
        result.outcome,
    )


def run_case(
    session: Session,
    settings: Settings,
    case: GoldenCase,
    officer_code: str,
) -> GoldenResult:
    """Execute a golden case using its declared evaluation path."""

    if case.execution is not None:
        if isinstance(case.execution, RuleExecution):
            return run_rule_case(case, case.execution)

        if isinstance(case.execution, ReadinessExecution):
            return run_readiness_case(case, case.execution)

        if isinstance(case.execution, RetrievalExecution):
            return run_retrieval_case(case, case.execution)

        if isinstance(case.execution, EscalationExecution):
            return run_escalation_case(case, case.execution)

        raise TypeError(
            f"Unsupported execution type for {case.id}: {type(case.execution).__name__}"
        )

    if case.exposure_id is not None:
        return run_exposure_case(
            session=session,
            settings=settings,
            case=case,
            officer_code=officer_code,
        )

    return GoldenResult(
        case_id=case.id,
        passed=False,
        expected_outcome=case.expected_outcome,
        failures=[
            "Golden case has no executable path. "
            "Add structured execution metadata or an exposure_id."
        ],
    )


def run_all_golden_cases(
    session: Session,
    settings: Settings,
    officer_code: str,
) -> list[GoldenResult]:
    """Run every version-controlled golden case."""

    cases = load_golden_cases()

    return [
        run_case(
            session=session,
            settings=settings,
            case=case,
            officer_code=officer_code,
        )
        for case in cases
    ]
