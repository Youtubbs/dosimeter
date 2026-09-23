""" Structure-aware chunking for regulatory corpus documents """

from __future__ import annotations

import hashlib
from dataclasses import dataclass

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 100

@dataclass(frozen=True)
class CorpusSection:
    """A section of a regulatory document extracted from Textract."""

    doc_id: str
    title: str
    doc_type: str
    status: str
    section_path: str
    page: int
    text: str


@dataclass(frozen=True)
class CorpusChunk:
    """A chunk ready to be indexed in the Knowledge Base."""

    text: str
    doc_id: str
    title: str
    doc_type: str
    section_path: str
    page: int
    chunk_id: str
    status: str
    size: int
    overlap: int


def create_chunk_id(
    doc_id: str,
    section_path: str,
    page: int,
    chunk_index: int,
    text: str,
) -> str:
    """Create a stable deterministic ID for a chunk."""

    raw = (
        f"{doc_id}|"
        f"{section_path}|"
        f"{page}|"
        f"{chunk_index}|"
        f"{text}"
    )

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def split_by_size(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks when it is too large."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")

    if chunk_overlap < 0:
        raise ValueError("chunk_overlap cannot be negative.")

    if chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap must be smaller than chunk_size."
        )

    text = text.strip()

    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = end - chunk_overlap

    return chunks


def chunk_section(
    section: CorpusSection,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[CorpusChunk]:
    """Chunk one regulatory section while preserving its metadata."""

    text_chunks = split_by_size(
        section.text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    chunks: list[CorpusChunk] = []

    for index, text in enumerate(text_chunks):
        chunk_id = create_chunk_id(
            doc_id=section.doc_id,
            section_path=section.section_path,
            page=section.page,
            chunk_index=index,
            text=text,
        )

        chunks.append(
            CorpusChunk(
                text=text,
                doc_id=section.doc_id,
                title=section.title,
                doc_type=section.doc_type,
                section_path=section.section_path,
                page=section.page,
                chunk_id=chunk_id,
                status=section.status,
                size=len(text),
                overlap=chunk_overlap if index > 0 else 0,
            )
        )

    return chunks


def chunk_sections(
    sections: list[CorpusSection],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[CorpusChunk]:
    """Chunk all extracted regulatory sections."""

    chunks: list[CorpusChunk] = []

    for section in sections:
        chunks.extend(
            chunk_section(
                section,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        )

    return chunks