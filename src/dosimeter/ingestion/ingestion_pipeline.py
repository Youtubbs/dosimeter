""" complete pipeline for ingestion
        uploads to s3 -> runs textract -> normalizes -> redacts -> report
"""

from .redact import redact_fields
from .normalize import normalize
from .report import create_report
from .s3 import upload_packet
from .textract import extract_artifact

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
