"""MCP Tool Adapter — wraps MCP tool definitions as LangChain BaseTool instances."""

from typing import Dict, Any, Optional, Callable
import json
import logging

from langchain_core.tools import BaseTool
from langchain_core.callbacks import CallbackManagerForToolRun
from pydantic import Field

logger = logging.getLogger(__name__)


class McpToolAdapter(BaseTool):
    """Adapts a single MCP tool into a LangChain BaseTool.

    Delegates actual execution to McpClientManager.call_tool().
    """

    mcp_service: str = Field(description="MCP service name (e.g., 'amap', 'weather')")
    mcp_tool_name: str = Field(description="Name of the tool on the MCP server")
    _executor: Optional[Callable] = None  # async callable (tool_name, args) -> result (svc captured in closure)

    def __init__(
        self,
        name: str,
        description: str,
        mcp_service: str,
        input_schema: Optional[Dict] = None,
        executor: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(
            name=name,
            description=description,
            mcp_service=mcp_service,
            mcp_tool_name=name,
            **kwargs,
        )
        self._executor = executor
        # Store raw input schema for reference but do NOT assign to args_schema.
        # args_schema must be a Pydantic model, not a dict — assigning a dict
        # causes infinite recursion in LangChain's bind_tools / convert_to_openai_tool.
        self._input_schema = input_schema

    def set_executor(self, executor: Callable):
        """Inject the executor function (from McpClientManager)."""
        self._executor = executor

    async def _arun(
        self,
        *args,
        _tool_input: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        """Execute the MCP tool."""
        if not self._executor:
            return json.dumps({"error": "MCP executor not configured"}, ensure_ascii=False)

        # Merge args from multiple sources
        tool_args = {}
        if _tool_input:
            tool_args.update(_tool_input)
        tool_args.update(kwargs)
        # Remove None values
        tool_args = {k: v for k, v in tool_args.items() if v is not None}

        try:
            result = await self._executor(self.mcp_tool_name, tool_args)
            if hasattr(result, 'content'):
                # MCP CallToolResult
                contents = []
                for c in result.content:
                    if hasattr(c, 'text'):
                        contents.append(c.text)
                    elif hasattr(c, 'data'):
                        contents.append(str(c.data))
                return "\n".join(contents)
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"MCP tool {self.mcp_service}.{self.mcp_tool_name} failed: {e}")
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    def _run(self, *args, **kwargs) -> str:
        """Synchronous execution not supported."""
        raise NotImplementedError("MCP tools only support async execution")


def create_langchain_tools(
    mcp_tools: list,
    service_name: str,
    executor: Callable,
) -> list:
    """Convert a list of MCP tool definitions to LangChain BaseTool instances.

    Args:
        mcp_tools: List of MCP tool dicts with keys: name, description, input_schema
        service_name: MCP service name
        executor: Async callable (tool_name, args) -> result (svc captured in closure)

    Returns:
        List of McpToolAdapter instances
    """
    tools = []
    for tool_def in mcp_tools:
        adapter = McpToolAdapter(
            name=tool_def["name"],
            description=tool_def.get("description", ""),
            mcp_service=service_name,
            input_schema=tool_def.get("input_schema"),
            executor=executor,
        )
        tools.append(adapter)
    return tools
