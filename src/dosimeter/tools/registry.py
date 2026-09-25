""" central place for all tools """
from dosimeter.tools.api_clients import ApiToolset
from dosimeter.tools.base import ToolRegistry
from dosimeter.tools.search_knowledge_base import SEARCH_KNOWLEDGE_BASE
from dosimeter.tools.transport import Transport


# add your tools as they are created
def build_tool_registry(transport: Transport) -> ToolRegistry:
    api_toolset = ApiToolset(transport=transport)

    return ToolRegistry(
        [
            SEARCH_KNOWLEDGE_BASE,
            *api_toolset.tools(),
        ]
    )
