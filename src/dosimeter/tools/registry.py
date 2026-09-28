"""Central registry construction for Dosimeter tools."""

from dosimeter.tools.api_clients import ApiToolset
from dosimeter.tools.base import ToolRegistry
from dosimeter.tools.proposals import proposal_tools
from dosimeter.tools.rules import rule_tools
from dosimeter.tools.search_knowledge_base import SEARCH_KNOWLEDGE_BASE
from dosimeter.tools.transport import Transport


def build_tool_registry(transport: Transport) -> ToolRegistry:
    """Build the complete registry of currently implemented Dosimeter tools."""

    api_toolset = ApiToolset(transport=transport)

    return ToolRegistry(
        [
            SEARCH_KNOWLEDGE_BASE,
            *api_toolset.tools(),
            *rule_tools(),
            *proposal_tools(),
        ]
    )
