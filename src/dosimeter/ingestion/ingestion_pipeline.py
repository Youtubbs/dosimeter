"""Complete pipeline for ingestion.

Uploads to S3 -> runs Textract -> applies Bedrock Guardrails ->
normalizes -> redacts -> reports.
"""

from dosimeter.guardrails.bedrock import (
    BedrockGuardrailOutcome,
    apply_guardrail,
)
from dosimeter.guardrails.events import (
    GuardrailEvent,
    GuardrailRemedy,
    create_guardrail_event,
)

from ..redaction import redact_fields
from .chunking import chunk_sections
from .corpus import process_corpus
from .normalize import normalize
from .report import create_report
from .s3 import upload_packet
from .sectioning import build_sections
from .textract import extract_artifact


def _guard_extracted_blocks(
    blocks: list[dict],
    *,
    artifact_name: str,
) -> tuple[list[dict], list[GuardrailEvent]]:
    """Apply Bedrock Guardrails to every extracted text string.

    Returns the original Textract blocks and any structured guardrail
    events created during inspection.
    """

    events: list[GuardrailEvent] = []

    for block in blocks:
        text = block.get("Text")

        if not isinstance(text, str) or not text.strip():
            continue

        result = apply_guardrail(
            text,
            source=f"artifact:{artifact_name}",
        )

        if (
            result.outcome == BedrockGuardrailOutcome.INTERVENED
            and result.prompt_attack_fired
        ):
            events.append(
                create_guardrail_event(
                    trigger="prompt_attack_filter_fired",
                    remedy=GuardrailRemedy.BLOCK_AND_ESCALATE,
                    source=result.source,
                    detail="Bedrock Prompt Attack filter intervened.",
                )
            )

    return blocks, events


def ingest_packet(packet_dir):
    artifacts = upload_packet(packet_dir)

    results = []

    for artifact in artifacts:
        artifact_name = artifact["s3_key"]

        blocks = extract_artifact(artifact_name)

        blocks, guardrail_events = _guard_extracted_blocks(
            blocks,
            artifact_name=artifact_name,
        )

        normalized = normalize(
            blocks=blocks,
            source_artifact=artifact_name,
        )

        redacted = redact_fields(normalized)

        report = create_report(redacted)

        results.append(
            {
                "report": report,
                "guardrail_events": guardrail_events,
            }
        )

    return results


def ingest_corpus():
    """Ingest the regulatory corpus and produce Knowledge Base chunks."""

    corpus_results = process_corpus()

    results = []

    for corpus_result in corpus_results:
        blocks = corpus_result.get("blocks", [])

        if not blocks:
            results.append(
                {
                    "document": corpus_result["document"],
                    "chunks": [],
                    "error": corpus_result.get(
                        "error",
                        "No Textract blocks returned.",
                    ),
                }
            )
            continue

        document = corpus_result["document"]
        doc_id = document.removesuffix(".pdf")

        if doc_id.startswith("CFR"):
            doc_type = "regulation"
            status = "in_force"
        else:
            doc_type = "preamble"
            status = "proposed"

        sections = build_sections(
            blocks,
            doc_id=doc_id,
            title=doc_id,
            doc_type=doc_type,
            status=status,
        )

        chunks = chunk_sections(sections)

        results.append(
            {
                "document": document,
                "sections": sections,
                "chunks": chunks,
            }
        )

    return results
