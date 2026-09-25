"""Knowledge-base retrieval tool."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from dosimeter.graph.state import Subject
from dosimeter.retrieval.retriever import get_retriever
from dosimeter.tools.base import Tool


Status = Literal["in_force", "proposed"]


class KnowledgeBaseSearchInput(BaseModel):
    """Arguments supplied by the model to search the regulatory corpus."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    k: int = Field(default=4, ge=1, le=10)
    status: Status | None = None


class KnowledgeBaseSource(BaseModel):
    """One retrieved regulatory source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    doc_id: str
    chunk_id: str
    title: str
    doc_type: str
    section_path: str
    page: int | None
    status: Status
    score: float
    text: str


class KnowledgeBaseSearchOutput(BaseModel):
    """Result returned by the knowledge-base search tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    found: bool
    query: str
    sources: list[KnowledgeBaseSource] = Field(default_factory=list)
    refusal_reason: str | None = None


def _search_knowledge_base(
    subject: Subject,
    arguments: KnowledgeBaseSearchInput,
) -> KnowledgeBaseSearchOutput:
    """Search the regulatory corpus and return grounded sources."""

    del subject

    retriever = get_retriever(
        k=arguments.k,
        status=arguments.status,
    )

    documents = retriever.invoke(arguments.query)

    if not documents:
        return KnowledgeBaseSearchOutput(
            found=False,
            query=arguments.query,
            sources=[],
            refusal_reason=("No regulatory evidence met the retrieval threshold for this query."),
        )

    sources: list[KnowledgeBaseSource] = []

    for document in documents:
        metadata = document.metadata

        sources.append(
            KnowledgeBaseSource(
                doc_id=str(metadata.get("doc_id", "")),
                chunk_id=str(metadata.get("chunk_id", "")),
                title=str(metadata.get("title", "")),
                doc_type=str(metadata.get("doc_type", "")),
                section_path=str(metadata.get("section_path", "")),
                page=(int(metadata["page"]) if metadata.get("page") is not None else None),
                status=metadata.get("status", "in_force"),
                score=float(metadata.get("score", 0.0)),
                text=document.page_content,
            )
        )

    return KnowledgeBaseSearchOutput(
        found=True,
        query=arguments.query,
        sources=sources,
    )


SEARCH_KNOWLEDGE_BASE = Tool(
    name="search_knowledge_base",
    description=(
        "Search the Dosimeter regulatory corpus for grounded evidence. "
        "Use status='in_force' when answering what regulation currently "
        "applies. Proposed sources may be retrieved when explicitly needed, "
        "but must be identified as proposed. If no evidence meets the "
        "retrieval threshold, return no evidence rather than guessing."
    ),
    input_model=KnowledgeBaseSearchInput,
    output_model=KnowledgeBaseSearchOutput,
    handler=_search_knowledge_base,
)
