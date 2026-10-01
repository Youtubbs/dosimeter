"""The dossier an assess turn left behind, rendered for the officer: the proposals, the
numbered sources they cite, the rule outcomes, and what the turn could not read."""

from typing import Any

from dosimeter.errors import GateError
from dosimeter.graph.nodes.eligibility import rule_results
from dosimeter.graph.nodes.reviewer import cited_source
from dosimeter.repository import Session, queries
from dosimeter.retrieval.retriever import fetch_chunk

DISCLOSURE = (
    "AI-generated draft. It describes rule outcomes and the evidence for them; verify every item "
    "before acting. "
)
SYNTHETIC_NOTICE = "Synthetic data: the exposure packets are fictional but the regulatory text is real NRC material."

# seven 20.1206 conditions R4 checks, each with the evidence fields that meet it
R4_CONDITIONS = {
    "(a) exceptional situation, no alternative": ["exceptional_situation", "alternatives_unavailable_or_impractical"],
    "(b) written authorization before the exposure": [
        "licensee_written_authorization",
        "employer_written_authorization",
        "authorization_before_exposure",
    ],
    "(c) worker informed and instructed": [
        "worker_informed_of_purpose",
        "worker_informed_of_estimated_dose_and_risks",
        "worker_instructed_in_alara_measures",
    ],
    "(d) prior lifetime doses ascertained": ["prior_lifetime_doses_ascertained"],
    "(e) annual and lifetime PSE limits": ["annual_pse_limit_satisfied", "lifetime_pse_limit_satisfied"],
    "(f) records kept and the 20.2204 report": ["required_records_maintained", "report_under_20_2204_submitted"],
    "(g) dose recorded and the worker told in writing": [
        "best_dose_estimate_recorded",
        "worker_informed_of_dose_in_writing",
        "worker_informed_within_30_days",
    ],
}


def latest_payload(session: Session, exposure_id: str) -> dict[str, Any]:
    row = queries.latest_dossier(session, exposure_id)
    if row is None:
        raise GateError("there is no dossier for this exposure yet; run assess first", exposure_id=exposure_id)
    return row.payload


def numbered_sources(payload: dict[str, Any]) -> list[tuple[str, dict | None]]:
    """Every citation once, in proposal order, with the retrieved chunk it names. Its position is its ref."""

    refs: list[tuple[str, dict | None]] = []
    for worker in payload.get("workers", []):
        for citation in payload["proposals"][worker].get("citations", []):
            if citation not in [seen for seen, _ in refs]:
                refs.append((citation, cited_source(citation, payload.get("sources", []))))
    return refs


def _status(source: dict | None) -> str:
    if source is None:
        return "unresolved: the turn did not retrieve this text"
    return "PROPOSED, NOT IN FORCE" if source.get("status") == "proposed" else str(source.get("status", ""))


def _source_line(ref: int, citation: str, source: dict | None) -> str:
    if source is None:
        return f"  [{ref}] {citation} - {_status(source)}"
    return (
        f"  [{ref}] {source.get('doc_id', '')} {source.get('title', '')}, {source.get('section_path', '')}, "
        f"page {source.get('page', '')} - {_status(source)}"
    )


def _amount(value: Any) -> str:
    if isinstance(value, dict) and "value" in value:
        site = f" ({value['site']})" if value.get("site") else ""
        return f"{value['value']} {value.get('unit', 'x ALI')}{site}"
    return str(value)


def _headline(kind: str, proposal: dict[str, Any]) -> str:
    if kind == "notification":
        found = "required" if proposal.get("notification_required") else "not required"
        return f"notification {found}, clock: {proposal.get('clock')}"
    if kind == "written_report":
        found = "required" if proposal.get("report_required") else "not required"
        return f"written report {found}, path: {proposal.get('reporting_path')}"
    found = "required" if proposal.get("report_required") else "not required"
    return f"equipment finding: {proposal.get('equipment_finding')}, report {found}"


def render_dossier(session: Session, exposure_id: str) -> str:
    """The latest dossier, with each claim citing its sources by number."""

    payload = latest_payload(session, exposure_id)
    refs = numbered_sources(payload)
    number = {citation: index for index, (citation, _) in enumerate(refs, start=1)}

    lines = [
        f"dossier for {exposure_id}",
        DISCLOSURE,
        SYNTHETIC_NOTICE,
        "",
        f"outcome     {payload.get('outcome') or 'partial: ' + (payload.get('partial') or {}).get('message', 'unfinished')}",
        f"escalation  {', '.join(payload.get('escalation_signals') or []) or 'no trigger fired'}",
    ]

    for worker in payload.get("workers", []):
        item = payload["proposals"][worker]
        cited = " ".join(f"[{number[citation]}]" for citation in item.get("citations", []))
        lines += ["", f"proposed by the {worker} worker", f"  {_headline(item['kind'], item['payload'])}"]
        lines.append(f"  {item['payload'].get('explanation', '')} {cited}".rstrip())

    results = rule_results(payload)
    if results:
        lines += ["", "rule outcomes"]
        for rule_id, result in sorted(results.items()):
            inputs = ", ".join(
                f"{name} {_amount(value)}"
                for name, value in (result.get("inputs_used") or {}).items()
                if value is not None
            )
            limits = ", ".join(f"{name} {_amount(value)}" for name, value in (result.get("threshold") or {}).items())
            lines.append(f"  {rule_id}: {result['outcome']} on {inputs or 'no inputs'}")
            if limits:
                lines.append(f"      against {limits}")

    r4 = results.get("R4")
    if r4 and r4.get("outcome") == "valid":
        evidence = r4.get("inputs_used") or {}
        lines += ["", "planned special exposure: the seven 20.1206 conditions"]
        for condition, fields in R4_CONDITIONS.items():
            met = all(evidence.get(field) is True for field in fields)
            lines.append(f"  {condition}: {'met' if met else 'not shown'} ({', '.join(fields)})")
        lines.append("  the 20.2204 report to the NRC Regional Office within 30 days is the substitute report")

    lines += ["", "sources"]
    lines += [_source_line(index, citation, source) for index, (citation, source) in enumerate(refs, start=1)]
    if not refs:
        lines.append("  none cited")

    report = queries.latest_ingestion_report(session, exposure_id)
    if report is not None and report.failures:
        lines += ["", "not read from the packet"]
        lines += [
            f"  {item['file_name']}: {item['reason_code']}" + (f" - {item['detail']}" if item.get("detail") else "")
            for item in report.failures
        ]

    return "\n".join(lines)


def render_sources(session: Session, exposure_id: str, ref: int | None = None) -> str:
    """Every cited source with its status, or the full text behind one of them."""

    payload = latest_payload(session, exposure_id)
    refs = numbered_sources(payload)

    if ref is None:
        lines = [f"sources cited in the dossier for {exposure_id}"]
        lines += [_source_line(index, citation, source) for index, (citation, source) in enumerate(refs, start=1)]
        return "\n".join(lines if refs else [*lines, "  none cited"])

    if not 1 <= ref <= len(refs):
        raise GateError(f"there is no source [{ref}]; this dossier cites {len(refs)}", ref=ref)

    citation, source = refs[ref - 1]
    if source is None:
        return f"[{ref}] {citation}\n{_status(source)}"

    # the text comes from the corpus itself, not from what the turn stored
    chunk = fetch_chunk(str(source.get("chunk_id", "")))
    text = chunk.page_content if chunk is not None else source.get("text", "")

    return "\n".join(
        [
            f"[{ref}] {source.get('doc_id', '')} {source.get('title', '')}",
            f"section   {source.get('section_path', '')}",
            f"page      {source.get('page', '')}",
            f"chunk id  {source.get('chunk_id', '')}",
            f"status    {_status(source)}",
            "",
            text,
        ]
    )
