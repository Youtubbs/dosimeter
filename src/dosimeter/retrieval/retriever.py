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

from dosimeter.aws.config import EMBED_MODEL_ID, AWS_REGION, BEDROCK_KB_ID

# this will change based on golden set rules
THRESHOLD = 0.4

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


class ScoreThresholdRetriever(BaseRetriever):
    """Retrieve the top-k local chunks that meet a similarity threshold."""

    store: InMemoryVectorStore
    k: int = 4
    threshold: float = THRESHOLD
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
    k: int = 4, threshold: float = THRESHOLD, status: Status | None = None
) -> BaseRetriever:
    """Build the local in-memory retriever for development."""

    chunks = load_corpus_chunks()

    embeddings = BedrockEmbeddings(
        model_id=EMBED_MODEL_ID,
        region_name=AWS_REGION,
    )

    store = InMemoryVectorStore.from_documents(
        documents=chunks,
        embedding=embeddings,
    )

    return ScoreThresholdRetriever(store=store, k=k, threshold=threshold, status=status)


def build_kb_retriever(
    k: int = 4,
    threshold: float = THRESHOLD,
    status: Status | None = None,
) -> BaseRetriever:
    """Build the production Amazon Bedrock Knowledge Base retriever."""

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
        knowledge_base_id=BEDROCK_KB_ID,
        region_name=AWS_REGION,
        retrieval_config={
            "vectorSearchConfiguration": vector_search_configuration,
        },
        min_score_confidence=threshold,
    )


def get_retriever(
    k: int = 4,
    threshold: float = THRESHOLD,
    status: Status | None = None,
) -> BaseRetriever:
    """Return the configured Dosimeter retriever."""

    if BEDROCK_KB_ID:
        return build_kb_retriever(
            k=k,
            threshold=threshold,
            status=status,
        )

    return build_local_retriever(k=k, threshold=threshold, status=status)
