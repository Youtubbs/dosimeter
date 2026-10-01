"""The Knowledge Base as a connector target on its AWS_IAM Gateway: signing, the request, and the documents."""

import socket
import threading
import time
from typing import Any

import httpx
import pytest
import uvicorn
from botocore.credentials import Credentials
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent
from mcp.types import Tool as McpTool

from dosimeter.aws.aws import SigV4HttpxAuth
from dosimeter.errors import ExternalServiceError
from dosimeter.graph.schemas import Subject
from dosimeter.retrieval import retriever as retrieval
from dosimeter.retrieval.retriever import (
    GatewayKnowledgeBaseRetriever,
    retrieval_results,
    retrieve_arguments,
)
from dosimeter.tools import search_knowledge_base as search_module
from dosimeter.tools.search_knowledge_base import KnowledgeBaseSearchInput

# nothing listens here, so every call is refused straight away
DEAD_GATEWAY = "http://127.0.0.1:1/mcp"

# passes requests through unsigned, in place of SigV4
NO_SIGNING = httpx.Auth()

RESULTS = [
    {
        "content": {"type": "TEXT", "text": "Each licensee shall control the occupational dose."},
        "score": 0.81,
        "location": {"type": "S3"},
        "metadata": {"doc_id": "CFR-20", "title": "10 CFR Part 20", "status": "in_force", "page": 3},
    },
    {
        "content": {"type": "TEXT", "text": "A barely related passage."},
        "score": 0.12,
        "metadata": {"doc_id": "CFR-34", "title": "10 CFR Part 34", "status": "in_force"},
    },
]

# stands in for the connector target: the Gateway prefixes the target name
stub = FastMCP("kb")
requests_seen: list[dict] = []


@stub.tool(name="corpusKb___Retrieve")
def retrieve(retrievalQuery: dict, retrievalConfiguration: dict | None = None) -> dict[str, Any]:
    """Queries a knowledge base and retrieves information from it."""

    requests_seen.append({"retrievalQuery": retrievalQuery, "retrievalConfiguration": retrievalConfiguration})
    return {"retrievalResults": RESULTS}


@pytest.fixture(scope="module")
def kb_url():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    server = uvicorn.Server(uvicorn.Config(stub.streamable_http_app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)

    yield f"http://127.0.0.1:{port}/mcp"

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(autouse=True)
def fresh_requests():
    requests_seen.clear()


def test_each_request_is_signed_for_agentcore() -> None:
    auth = SigV4HttpxAuth(credentials=Credentials("AKIDEXAMPLE", "secret"), region="us-east-1")
    request = httpx.Request("POST", "https://kb.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp", content=b"{}")

    signed = next(auth.auth_flow(request))

    assert signed.headers["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/")
    assert "/us-east-1/bedrock-agentcore/aws4_request" in signed.headers["Authorization"]
    assert "X-Amz-Date" in signed.headers


def test_the_request_keeps_only_the_fields_the_tool_declares() -> None:
    request = {"retrievalQuery": {"text": "dose"}, "retrievalConfiguration": {"x": 1}}
    narrow = McpTool(name="t___Retrieve", inputSchema={"type": "object", "properties": {"retrievalQuery": {}}})
    open_schema = McpTool(name="t___Retrieve", inputSchema={"type": "object"})

    assert retrieve_arguments(narrow, request) == {"retrievalQuery": {"text": "dose"}}
    assert retrieve_arguments(open_schema, request) == request


def test_results_come_from_structured_content_or_json_text() -> None:
    structured = CallToolResult(content=[], structuredContent={"retrievalResults": RESULTS})
    text = CallToolResult(content=[TextContent(type="text", text='{"retrievalResults": []}')])
    garbled = CallToolResult(content=[TextContent(type="text", text="not json")])

    assert len(retrieval_results(structured)) == 2
    assert retrieval_results(text) == []
    with pytest.raises(ExternalServiceError):
        retrieval_results(garbled)


def test_documents_come_back_with_their_citation_fields_above_the_threshold(kb_url: str) -> None:
    retriever = GatewayKnowledgeBaseRetriever(url=kb_url, k=3, threshold=0.4, status="in_force", auth=NO_SIGNING)

    documents = retriever.invoke("occupational dose limits")

    assert [document.metadata["doc_id"] for document in documents] == ["CFR-20"]
    assert documents[0].metadata["title"] == "10 CFR Part 20"
    assert documents[0].metadata["score"] == 0.81
    assert documents[0].page_content.startswith("Each licensee")

    [sent] = requests_seen
    assert sent["retrievalQuery"] == {"text": "occupational dose limits"}
    assert sent["retrievalConfiguration"]["managedSearchConfiguration"] == {
        "numberOfResults": 3,
        "filter": {"equals": {"key": "status", "value": "in_force"}},
    }


def test_an_unreachable_kb_gateway_is_a_typed_failure() -> None:
    retriever = GatewayKnowledgeBaseRetriever(url=DEAD_GATEWAY, threshold=0.4, auth=NO_SIGNING)

    with pytest.raises(ExternalServiceError, match="knowledge base Gateway is unreachable"):
        retriever.invoke("dose")


def test_the_kb_gateway_setting_chooses_the_gateway_retriever(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = retrieval.get_settings().model_copy(update={"kb_gateway_url": "https://kb.example/mcp"})
    monkeypatch.setattr(retrieval, "get_settings", lambda: settings)

    chosen = retrieval.get_retriever(k=2, status="in_force")

    assert isinstance(chosen, GatewayKnowledgeBaseRetriever)
    assert (chosen.url, chosen.k, chosen.status) == ("https://kb.example/mcp", 2, "in_force")


def test_the_search_tool_cites_what_came_through_the_gateway(kb_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        search_module,
        "get_retriever",
        lambda k, status: GatewayKnowledgeBaseRetriever(url=kb_url, k=k, threshold=0.4, status=status, auth=NO_SIGNING),
    )
    subject = Subject(session_id="s", officer_id=1, officer_code="OFF-101", exposure_id="EXP-2026-0412")

    output = search_module._search_knowledge_base(subject, KnowledgeBaseSearchInput(query="occupational dose"))

    assert output.found
    assert output.sources[0].doc_id == "CFR-20"
    assert output.sources[0].title == "10 CFR Part 20"
