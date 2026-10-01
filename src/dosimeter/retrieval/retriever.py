"""Create retrievers for the Dosimeter regulatory corpus."""

import asyncio
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from langchain_aws import AmazonKnowledgeBasesRetriever, BedrockEmbeddings
from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.vectorstores import InMemoryVectorStore
from mcp.types import CallToolResult
from mcp.types import Tool as McpTool

from dosimeter.aws.aws import SigV4HttpxAuth, client_config
from dosimeter.aws.gateway import call_gateway_tool
from dosimeter.config.settings import get_settings
from dosimeter.errors import ExternalServiceError

PROJECT_ROOT = Path(__file__).resolve().parents[3]
KB_DIR = PROJECT_ROOT / "kb"

Status = Literal["in_force", "proposed"]

# the knowledge base connector target exposes the Bedrock Retrieve API as this tool
KB_OPERATION = "Retrieve"

# a managed knowledge base rejects vectorSearchConfiguration; both take numberOfResults and filter
SEARCH_CONFIGURATION_KEY = "managedSearchConfiguration"


def load_corpus_chunks() -> list[Document]:
    """Load pre-chunked corpus documents and their metadata."""

    chunks: list[Document] = []

    for path in sorted(KB_DIR.glob("**/*.txt")):
        # Skip anything that might accidentally match a metadata file
        if path.name.endswith(".metadata.json"):
            continue

        metadata_path = Path(f"{path}.metadata.json")

        metadata: dict = {}

        if metadata_path.exists():
            raw_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

            metadata_attributes = raw_metadata.get(
                "metadataAttributes",
                {},
            )

            for key, value in metadata_attributes.items():
                metadata_value = value.get("value", {})

                if "stringValue" in metadata_value:
                    metadata[key] = metadata_value["stringValue"]
                elif "numberValue" in metadata_value:
                    metadata[key] = metadata_value["numberValue"]

        chunks.append(
            Document(
                page_content=path.read_text(encoding="utf-8"),
                metadata=metadata,
            )
        )

    return chunks


def fetch_chunk(chunk_id: str) -> Document | None:
    """One corpus chunk by id, read from the same files the Knowledge Base was built from."""

    return next((chunk for chunk in load_corpus_chunks() if chunk.metadata.get("chunk_id") == chunk_id), None)


class ScoreThresholdRetriever(BaseRetriever):
    """Retrieve the top-k local chunks that meet a similarity threshold."""

    store: InMemoryVectorStore
    k: int = 4
    threshold: float
    status: Status | None = None

    model_config = {"arbitrary_types_allowed": True}

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:

        hits = self.store.similarity_search_with_score(
            query,
            k=self.k,
        )

        documents: list[Document] = []

        for document, score in hits:
            if score < self.threshold:
                continue

            if self.status is not None and document.metadata.get("status") != self.status:
                continue

            # search_knowledge_base reports the score with each source
            documents.append(
                Document(
                    page_content=document.page_content,
                    metadata={
                        **document.metadata,
                        "score": float(score),
                    },
                )
            )

        return documents


@lru_cache(maxsize=None)
def build_local_retriever(
    k: int = 4, threshold: float | None = None, status: Status | None = None
) -> BaseRetriever:
    """Build the local in-memory retriever for development."""

    settings = get_settings()
    chunks = load_corpus_chunks()

    embeddings = BedrockEmbeddings(
        model_id=settings.bedrock_embed_model_id,
        region_name=settings.aws_region,
        credentials_profile_name=settings.aws_profile,
        config=client_config(),
    )

    store = InMemoryVectorStore.from_documents(
        documents=chunks,
        embedding=embeddings,
    )

    return ScoreThresholdRetriever(
        store=store,
        k=k,
        threshold=settings.similarity_threshold if threshold is None else threshold,
        status=status,
    )


def build_kb_retriever(
    k: int = 4,
    threshold: float | None = None,
    status: Status | None = None,
) -> BaseRetriever:
    """Build the production Amazon Bedrock managed Knowledge Base retriever."""
def flatten_citation_metadata(documents: list[Document], threshold: float) -> list[Document]:
    """Lift doc_id, title, section_path, page and status out of source_metadata, and drop weak chunks."""

    kept: list[Document] = []

    for document in documents:
        metadata = {**document.metadata}
        metadata.update(metadata.pop("source_metadata", {}))

        if float(metadata.get("score", 0.0)) < threshold:
            continue

        kept.append(Document(page_content=document.page_content, metadata=metadata))

    return kept


def retrieval_configuration(k: int, status: Status | None) -> dict:
    """The Retrieve request's retrievalConfiguration: the top k chunks, filtered on status when asked for."""

    configuration: dict = {"numberOfResults": k}

    if status is not None:
        configuration["filter"] = {
            "equals": {
                "key": "status",
                "value": status,
            }
        }

    return {SEARCH_CONFIGURATION_KEY: configuration}


class CitedKnowledgeBasesRetriever(AmazonKnowledgeBasesRetriever):
    """The Bedrock retriever, with the citation fields lifted to the top of each document's metadata."""

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:

        documents = super()._get_relevant_documents(query, run_manager=run_manager)

        # min_score_confidence already dropped the weak chunks
        return flatten_citation_metadata(documents, threshold=0.0)


def build_kb_retriever(
    k: int = 4,
    threshold: float | None = None,
    status: Status | None = None,
) -> BaseRetriever:
    """Build the production Amazon Bedrock Knowledge Base retriever."""

    settings = get_settings()

    return CitedKnowledgeBasesRetriever(
        knowledge_base_id=settings.knowledge_base_id,
        region_name=settings.aws_region,
        credentials_profile_name=settings.aws_profile,
        config=client_config(),
        retrieval_config=retrieval_configuration(k, status),
        min_score_confidence=settings.similarity_threshold if threshold is None else threshold,
    )


class GatewayKnowledgeBaseRetriever(BaseRetriever):
    """Retrieve from the Knowledge Base through its connector target on the AgentCore Gateway."""

    url: str
    k: int = 4
    threshold: float
    status: Status | None = None
    # SigV4 with our credentials when unset
    auth: Any = None

    model_config = {"arbitrary_types_allowed": True}

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:

        request = {
            "retrievalQuery": {"text": query.strip()},
            "retrievalConfiguration": retrieval_configuration(self.k, self.status),
        }

        try:
            result = asyncio.run(
                call_gateway_tool(
                    self.url,
                    KB_OPERATION,
                    lambda tool: retrieve_arguments(tool, request),
                    auth=self.auth or SigV4HttpxAuth(),
                )
            )
        except ExternalServiceError:
            raise
        except Exception as error:
            raise ExternalServiceError(
                "the knowledge base Gateway is unreachable",
                detail=f"{type(error).__name__}: {error}",
            ) from error

        if result.isError:
            raise ExternalServiceError("the knowledge base Gateway refused the search", detail=_result_text(result))

        # the same conversion the direct retriever uses, so both paths return the same documents
        converted = AmazonKnowledgeBasesRetriever._retrieval_results_to_documents(retrieval_results(result))

        return flatten_citation_metadata(converted, threshold=self.threshold)


def retrieve_arguments(tool: McpTool, request: dict) -> dict:
    """The Retrieve request, keeping only the fields the Gateway tool declares."""

    properties = (tool.inputSchema or {}).get("properties") or {}
    if not properties:
        return request

    return {key: value for key, value in request.items() if key in properties}


def retrieval_results(result: CallToolResult) -> list[dict]:
    payload = result.structuredContent

    if payload is None:
        text = _result_text(result)
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError as error:
            raise ExternalServiceError("the knowledge base Gateway answered with no results", detail=text) from error

    return list(payload.get("retrievalResults", [])) if isinstance(payload, dict) else []


def _result_text(result: CallToolResult) -> str:
    return "".join(getattr(block, "text", "") for block in result.content)


def build_gateway_kb_retriever(
    k: int = 4,
    threshold: float | None = None,
    status: Status | None = None,
) -> BaseRetriever:
    """Build the Knowledge Base retriever that goes through the AgentCore Gateway."""

    settings = get_settings()

    return GatewayKnowledgeBaseRetriever(
        url=settings.kb_gateway_url,
        k=k,
        threshold=settings.similarity_threshold if threshold is None else threshold,
        status=status,
    )


def get_retriever(
    k: int = 4,
    threshold: float | None = None,
    status: Status | None = None,
) -> BaseRetriever:
    """Return the configured Dosimeter retriever."""

    if get_settings().kb_gateway_url:
        return build_gateway_kb_retriever(
            k=k,
            threshold=threshold,
            status=status,
        )

    if get_settings().knowledge_base_id:
        return build_kb_retriever(
            k=k,
            threshold=threshold,
            status=status,
        )

    return build_local_retriever(k=k, threshold=threshold, status=status)
