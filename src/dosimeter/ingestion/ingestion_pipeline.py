"""complete pipeline for ingestion
uploads to s3 -> runs textract -> normalizes -> redacts -> report
"""

from ..redaction import redact_fields
from .normalize import normalize
from .report import create_report
from .s3 import upload_packet
from .textract import extract_artifact

from .chunking import chunk_sections
from .sectioning import build_sections
from .corpus import process_corpus

def ingest_packet(packet_dir):
    artifacts = upload_packet(packet_dir)

    results = []

    for artifact in artifacts:
        blocks = extract_artifact(artifact["s3_key"])

        normalized = normalize(
            blocks=blocks,
            source_artifact=artifact["s3_key"],
        )

        redacted = redact_fields(normalized)

        report = create_report(redacted)

        results.append(report)

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
