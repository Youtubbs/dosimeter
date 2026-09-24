"""Export regulatory corpus chunks for Amazon Bedrock Knowledge Bases."""
import json
from pathlib import Path

from .chunking import CorpusChunk

def metadata_for_chunk(chunk: CorpusChunk) -> dict:
    """Build Bedrock Knowledge Base metadata for one chunk."""

    return {
        "metadataAttributes": {
            "doc_id": {
                "value": {
                    "type": "STRING",
                    "stringValue": chunk.doc_id,
                }
            },
            "title": {
                "value": {
                    "type": "STRING",
                    "stringValue": chunk.title,
                }
            },
            "doc_type": {
                "value": {
                    "type": "STRING",
                    "stringValue": chunk.doc_type,
                }
            },
            "section_path": {
                "value": {
                    "type": "STRING",
                    "stringValue": chunk.section_path,
                }
            },
            "page": {
                "value": {
                    "type": "NUMBER",
                    "numberValue": chunk.page,
                }
            },
            "chunk_id": {
                "value": {
                    "type": "STRING",
                    "stringValue": chunk.chunk_id,
                }
            },
            "status": {
                "value": {
                    "type": "STRING",
                    "stringValue": chunk.status,
                }
            },
        }
    }


def write_chunk(chunk: CorpusChunk, output_dir: Path) -> tuple[Path, Path]:
    """Write one chunk and its metadata sidecar."""

    document_dir = output_dir / chunk.doc_id
    document_dir.mkdir(parents=True, exist_ok=True)

    text_path = document_dir / f"{chunk.chunk_id}.txt"
    metadata_path = document_dir / f"{chunk.chunk_id}.txt.metadata.json"

    text_path.write_text(chunk.text, encoding="utf-8")

    metadata_path.write_text(
        json.dumps(metadata_for_chunk(chunk), indent=2),
        encoding="utf-8",
    )

    return text_path, metadata_path

def export_chunks(
    corpus_results: list[dict],
    output_dir: Path,
) -> list[tuple[Path, Path]]:
    """Export all corpus chunks and their metadata."""

    output_dir.mkdir(parents=True, exist_ok=True)

    exported = []

    for result in corpus_results:
        for chunk in result.get("chunks", []):
            exported.append(
                write_chunk(
                    chunk=chunk,
                    output_dir=output_dir,
                )
            )

    return exported
