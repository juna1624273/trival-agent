"""Tool Registry — maps agent types to their MCP tool sets."""

from typing import Dict, List
from langchain_core.tools import BaseTool


class ToolRegistry:
    """Central registry for MCP tools organized by agent type.

    Each agent type has a set of LangChain BaseTools bound to it.
    Supports runtime tool addition and per-agent filtering.
    """

    def __init__(self):
        self._agent_tools: Dict[str, List[BaseTool]] = {}
        self._tool_index: Dict[str, BaseTool] = {}  # tool_name -> tool

    def register_for_agent(self, agent_type: str, tools: List[BaseTool]):
        """Register tools for a specific agent type."""
        if agent_type not in self._agent_tools:
            self._agent_tools[agent_type] = []
        self._agent_tools[agent_type].extend(tools)
        for tool in tools:
            self._tool_index[tool.name] = tool

    def get_tools_for_agent(self, agent_type: str) -> List[BaseTool]:
        """Get all tools available to an agent type."""
        return self._agent_tools.get(agent_type, [])

    def get_tool_by_name(self, tool_name: str) -> BaseTool:
        """Look up a tool by name."""
        return self._tool_index.get(tool_name)

    def list_agent_types(self) -> List[str]:
        """List all registered agent types."""
        return list(self._agent_tools.keys())

    def list_tool_names(self, agent_type: str = None) -> List[str]:
        """List tool names, optionally filtered by agent type."""
        if agent_type:
            return [t.name for t in self._agent_tools.get(agent_type, [])]
        return list(self._tool_index.keys())


# Global singleton
tool_registry = ToolRegistry()
