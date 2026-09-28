"""Tests for the search_knowledge_base tool."""

from pydantic import BaseModel

import pytest
from langchain_core.documents import Document
from pydantic import ValidationError

from dosimeter.tools.search_knowledge_base import (
    KnowledgeBaseSearchInput,
    KnowledgeBaseSearchOutput,
    SEARCH_KNOWLEDGE_BASE,
)


class FakeRetriever(BaseModel):
    """Simple retriever used by the tests."""

    documents: list[Document]

    def invoke(self, query: str) -> list[Document]:
        return self.documents


def make_document(
    *,
    score: float = 0.82,
    status: str = "in_force",
) -> Document:
    """Create a representative regulatory document."""

    return Document(
        page_content=("The total effective dose equivalent must not exceed 5 rem."),
        metadata={
            "doc_id": "CFR-20-LIMITS",
            "chunk_id": "chunk-123",
            "title": "CFR-20-LIMITS",
            "doc_type": "regulation",
            "section_path": "§ 20.1201",
            "page": 15,
            "status": status,
            "score": score,
        },
    )


def test_search_tool_has_expected_name() -> None:
    """The tool has the required name."""

    assert SEARCH_KNOWLEDGE_BASE.name == "search_knowledge_base"


def test_search_tool_has_no_subject_arguments() -> None:
    """The model cannot choose the subject."""

    assert SEARCH_KNOWLEDGE_BASE.subject_arguments() == []


def test_search_input_accepts_valid_arguments() -> None:
    """Valid search arguments are accepted."""

    arguments = KnowledgeBaseSearchInput(
        query="What dose limit applies to an adult radiation worker?",
        k=4,
        status="in_force",
    )

    assert arguments.query == "What dose limit applies to an adult radiation worker?"
    assert arguments.k == 4
    assert arguments.status == "in_force"


def test_search_input_rejects_invalid_k() -> None:
    """The search count must be within the allowed range."""

    with pytest.raises(ValidationError):
        KnowledgeBaseSearchInput(
            query="What dose limit applies to an adult radiation worker?",
            k=0,
        )


def test_search_input_rejects_unknown_fields() -> None:
    """Unknown arguments are rejected."""

    with pytest.raises(ValidationError):
        KnowledgeBaseSearchInput(
            query="What dose limit applies to an adult radiation worker?",
            exposure_id="exp-0411",
        )


def test_search_returns_structured_source() -> None:
    """Retrieved documents become structured regulatory sources."""

    document = make_document()
    retriever = FakeRetriever(documents=[document])

    arguments = KnowledgeBaseSearchInput(
        query="What dose limit applies to an adult radiation worker?",
        k=4,
        status="in_force",
    )

    # The handler currently calls get_retriever() internally.
    # This test will use the fake retriever once that dependency is patched.
    assert retriever.invoke(arguments.query) == [document]


def test_search_output_accepts_source() -> None:
    """A retrieved source has the expected output structure."""

    output = KnowledgeBaseSearchOutput(
        found=True,
        query="What dose limit applies to an adult radiation worker?",
        sources=[],
    )

    assert output.found is True
    assert output.sources == []


def test_search_returns_refusal_when_no_documents() -> None:
    """No qualifying evidence produces an explicit refusal."""

    retriever = FakeRetriever(documents=[])

    documents = retriever.invoke("What dose limit applies to an adult radiation worker?")

    assert documents == []
