"""Central registry construction for Dosimeter tools."""

from dosimeter.tools.dispatcher import Tool, build_registry
from dosimeter.tools.proposals import proposal_tools
from dosimeter.tools.rules import rule_tools
from dosimeter.tools.search_knowledge_base import SEARCH_KNOWLEDGE_BASE
from dosimeter.tools.tools import ApiToolset
from dosimeter.tools.transport import HttpTransport


def build_tool_registry(transport: HttpTransport) -> dict[str, Tool]:
    """Build the complete registry of currently implemented Dosimeter tools."""

    api_toolset = ApiToolset(transport=transport)

    return build_registry(
        [
            SEARCH_KNOWLEDGE_BASE,
            *api_toolset.tools(),
            *rule_tools(),
            *proposal_tools(),
        ]
    )
