"""Create retrievers for the Dosimeter regulatory corpus."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from langchain_aws import AmazonKnowledgeBasesRetriever, BedrockEmbeddings
from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.vectorstores import InMemoryVectorStore

from dosimeter.config.settings import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
KB_DIR = PROJECT_ROOT / "kb"

Status = Literal["in_force", "proposed"]


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
            raw_metadata = json.loads(
                metadata_path.read_text(encoding="utf-8")
            )

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


class ScoreThresholdRetriever(BaseRetriever):
    """Retrieve the top-k local chunks that meet a similarity threshold."""

    store: InMemoryVectorStore
    k: int = 4
    threshold: float
    status : Status | None = None

    model_config = {"arbitrary_types_allowed": True}

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:

        hits = self.store.similarity_search_with_score(
            query,
            k=self.k,
        )

        documents = [
            document
            for document, score in hits
            if score >= self.threshold
        ]

        if self.status is not None:
            documents = [
                document
                for document in documents
                if document.metadata.get("status") == self.status
            ]

        return documents

@lru_cache(maxsize=None)
def build_local_retriever(
    k: int = 4,
    threshold: float | None = None,
    status : Status | None = None
) -> BaseRetriever:
    """Build the local in-memory retriever for development."""

    settings = get_settings()
    chunks = load_corpus_chunks()

    embeddings = BedrockEmbeddings(
        model_id=settings.bedrock_embed_model_id,
        region_name=settings.aws_region,
        credentials_profile_name=settings.aws_profile,
    )

    store = InMemoryVectorStore.from_documents(
        documents=chunks,
        embedding=embeddings,
    )

    return ScoreThresholdRetriever(
        store=store,
        k=k,
        threshold=settings.similarity_threshold if threshold is None else threshold,
        status=status
    )


def build_kb_retriever(
    k: int = 4,
    threshold: float | None = None,
    status: Status | None = None,
) -> BaseRetriever:
    """Build the production Amazon Bedrock Knowledge Base retriever."""

    settings = get_settings()

    vector_search_configuration = {
        "numberOfResults": k,
    }

    if status is not None:
        vector_search_configuration["filter"] = {
            "equals": {
                "key": "status",
                "value": status,
            }
        }

    return AmazonKnowledgeBasesRetriever(
        knowledge_base_id=settings.knowledge_base_id,
        region_name=settings.aws_region,
        credentials_profile_name=settings.aws_profile,
        retrieval_config={
            "vectorSearchConfiguration": vector_search_configuration,
        },
        min_score_confidence=settings.similarity_threshold if threshold is None else threshold,
    )


def get_retriever(
    k: int = 4,
    threshold: float | None = None,
    status: Status | None = None,
) -> BaseRetriever:
    """Return the configured Dosimeter retriever."""

    if get_settings().knowledge_base_id:
        return build_kb_retriever(
            k=k,
            threshold=threshold,
            status=status,
        )

    return build_local_retriever(
        k=k,
        threshold=threshold,
        status=status
    )
