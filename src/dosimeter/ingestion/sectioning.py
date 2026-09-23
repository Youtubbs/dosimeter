"""Convert Textract output into structure-aware corpus sections."""
import re
from typing import Any

from .chunking import CorpusSection


def get_text_lines(
    blocks: list[dict[str, Any]],
) -> list[tuple[int, str]]:
    """Extract LINE text from Textract blocks with page numbers."""

    lines: list[tuple[int, str]] = []

    for block in blocks:
        if block.get("BlockType") != "LINE":
            continue

        text = block.get("Text", "").strip()
        page = block.get("Page")

        if not text or not page:
            continue

        lines.append((int(page), text))

    return lines


def is_section_heading(text: str) -> bool:
    """Return True when a line represents a regulatory section heading."""

    text = text.strip()

    # CFR sections such as:
    # § 20.1201
    # § 30.71
    # § 34.20
    return bool(
        re.match(
            r"^§\s*\d+(?:\.\d+)+\b",
            text,
        )
    )


def extract_section_path(text: str) -> str:
    """Extract the CFR section number from a heading."""

    match = re.match(
        r"^(§\s*\d+(?:\.\d+)+)",
        text.strip(),
    )

    if match:
        return match.group(1)

    return text.strip()


def build_sections(
    blocks: list[dict[str, Any]],
    *,
    doc_id: str,
    title: str,
    doc_type: str,
    status: str,
) -> list[CorpusSection]:
    """
    Convert Textract LINE blocks into CorpusSection objects.

    A new section begins whenever a regulatory section heading
    is encountered.
    """

    if status not in {"in_force", "proposed"}:
        raise ValueError(
            "status must be 'in_force' or 'proposed'."
        )

    lines = get_text_lines(blocks)

    sections: list[CorpusSection] = []

    current_section_path = "root"
    current_page = 1
    current_lines: list[str] = []

    for page, text in lines:

        if is_section_heading(text):
            if current_lines:
                sections.append(
                    CorpusSection(
                        doc_id=doc_id,
                        title=title,
                        doc_type=doc_type,
                        status=status,
                        section_path=current_section_path,
                        page=current_page,
                        text="\n".join(current_lines).strip(),
                    )
                )

            current_section_path = extract_section_path(text)
            current_page = page
            current_lines = [text]
            continue

        current_lines.append(text)

    if current_lines:
        sections.append(
            CorpusSection(
                doc_id=doc_id,
                title=title,
                doc_type=doc_type,
                status=status,
                section_path=current_section_path,
                page=current_page,
                text="\n".join(current_lines).strip(),
            )
        )

    return sections
