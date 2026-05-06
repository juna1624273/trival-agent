"""Unified MCP Client Manager.

Manages connections to 6 MCP servers. All connections are lazy —
they happen on first tool call, never at startup.
When MCP is unavailable, falls back to direct API calls.
"""

import asyncio
import logging
from typing import Dict, List, Any
from dataclasses import dataclass

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from src.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class McpServiceConfig:
    name: str
    url: str
    api_key: str = ""


class McpClientManager:
    """Lazy MCP client manager. Never blocks startup."""

    def __init__(self):
        self._service_configs: Dict[str, McpServiceConfig] = {}
        self._sessions: Dict[str, ClientSession] = {}
        self._http_clients: Dict[str, Any] = {}  # streamablehttp client for cleanup
        self._tools: Dict[str, List[Dict]] = {}
        self._connection_errors: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._initialize_configs()

    def _initialize_configs(self):
        self._service_configs = {
            "amap":    McpServiceConfig(name="amap",    url=settings.amap_mcp_url,    api_key=settings.amap_api_key),
            "railway": McpServiceConfig(name="railway", url=settings.railway_mcp_url),
            "flight":  McpServiceConfig(name="flight",  url=settings.flight_mcp_url),
            "weather": McpServiceConfig(name="weather", url=settings.weather_mcp_url, api_key=settings.weather_api_key),
            "hotel":   McpServiceConfig(name="hotel",   url=settings.hotel_mcp_url),
            "search":  McpServiceConfig(name="search",  url=settings.search_mcp_url,  api_key=settings.search_api_key),
        }

    # ---- Startup (non-blocking) ----

    async def connect_all(self) -> Dict[str, bool]:
        """No-op at startup. MCP connections are fully lazy."""
        configured = [n for n, c in self._service_configs.items() if c.url]
        if not configured:
            logger.info("No MCP URLs configured — using direct API for all services")
            return {}
        logger.info(f"MCP URLs configured for {len(configured)} services: {configured}")
        logger.info("MCP connections are lazy — will attempt on first tool call")
        return {n: False for n in self._service_configs}

    # ---- Lazy connect (called on first tool use) ----

    async def connect(self, service_name: str) -> bool:
        """Try to connect to one MCP server. Fails silently — API fallback takes over."""
        config = self._service_configs.get(service_name)
        if not config or not config.url:
            return False

        async with self._lock:
            if service_name in self._sessions:
                return True

            try:
                logger.debug(f"MCP {service_name}: trying {config.url}")
                client = streamable_http_client(config.url, timeout=8.0)
                read_stream, write_stream, _ = await client.__aenter__()
                self._http_clients[service_name] = client
                session = ClientSession(read_stream, write_stream)
                await session.__aenter__()
                await session.initialize()

                tools_result = await session.list_tools()
                tools = [{
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema,
                } for t in tools_result.tools]

                self._sessions[service_name] = session
                self._tools[service_name] = tools
                self._connection_errors.pop(service_name, None)
                logger.info(f"MCP {service_name}: connected, {len(tools)} tools")
                return True

            except Exception as e:
                msg = str(e)[:100]
                logger.debug(f"MCP {service_name}: unavailable ({msg})")
                self._connection_errors[service_name] = msg
                return False

    # ---- Tool access ----

    async def get_tools(self, service_name: str) -> List[Dict]:
        tools = self._tools.get(service_name)
        if tools:
            return tools
        return _get_virtual_tools(service_name)

    async def call_tool(self, service_name: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool. MCP first, API fallback second."""
        # Try MCP if connected (or try once to connect)
        session = self._sessions.get(service_name)
        if session is None:
            # Try one lazy connect
            await self.connect(service_name)
            session = self._sessions.get(service_name)

        if session is not None:
            try:
                result = await session.call_tool(tool_name, arguments)
                return _format_mcp_result(result)
            except Exception as e:
                logger.debug(f"MCP call failed ({service_name}.{tool_name}): {e}")

        # API fallback
        from src.mcp.api_fallback import execute_tool
        return await execute_tool(service_name, tool_name, arguments)

    # ---- Housekeeping ----

    def is_connected(self, service_name: str) -> bool:
        return service_name in self._sessions

    @property
    def connected_services(self) -> List[str]:
        return list(self._sessions.keys())

    async def disconnect_all(self):
        for name in list(self._sessions.keys()):
            session = self._sessions.pop(name, None)
            if session:
                try:
                    await session.__aexit__(None, None, None)
                except Exception:
                    pass
            http_client = self._http_clients.pop(name, None)
            if http_client:
                try:
                    await http_client.__aexit__(None, None, None)
                except Exception:
                    pass
            self._tools.pop(name, None)

    # ---- Agent mapping ----

    AGENT_SERVICE_MAP = {
        "transport": ["railway", "flight"],
        "maps":     ["amap"],
        "weather":  ["weather"],
        "hotel":    ["hotel"],
        "search":   ["search"],
        "file":     [],
    }

    async def get_agent_tools(self, agent_type: str) -> List[Dict]:
        all_tools = []
        for svc in self.AGENT_SERVICE_MAP.get(agent_type, []):
            tools = await self.get_tools(svc)
            for t in tools:
                t["_mcp_service"] = svc
            all_tools.extend(tools)
        return all_tools


def _format_mcp_result(result) -> str:
    """Extract text from MCP CallToolResult into a string."""
    if isinstance(result, str):
        return result
    if hasattr(result, 'content'):
        parts = []
        for c in result.content:
            if hasattr(c, 'text'):
                parts.append(c.text)
            elif hasattr(c, 'data'):
                parts.append(str(c.data))
        return "\n".join(parts) if parts else ""
    return str(result)


# ============================================================
# Virtual tool definitions — used when MCP is unavailable
# ============================================================

_VIRTUAL_TOOLS: Dict[str, List[Dict]] = {
    "amap": [
        {"name": "geocode", "description": "地址转经纬度 (高德API)", "_mcp_service": "amap",
         "input_schema": {"type": "object", "properties": {"address": {"type": "string"}, "city": {"type": "string"}}}},
        {"name": "search_poi", "description": "搜索POI (高德API)", "_mcp_service": "amap",
         "input_schema": {"type": "object", "properties": {"keywords": {"type": "string"}, "city": {"type": "string"}, "radius": {"type": "integer"}}}},
        {"name": "direction", "description": "路径规划 (高德API)", "_mcp_service": "amap",
         "input_schema": {"type": "object", "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}, "mode": {"type": "string"}}}},
    ],
    "weather": [
        {"name": "get_forecast", "description": "天气预报 (OpenWeatherMap/wttr.in)", "_mcp_service": "weather",
         "input_schema": {"type": "object", "properties": {"city": {"type": "string"}, "days": {"type": "integer"}}}},
    ],
    "search": [
        {"name": "web_search", "description": "网页搜索 (Tavily/DuckDuckGo)", "_mcp_service": "search",
         "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "num_results": {"type": "integer"}}}},
        {"name": "search_attractions", "description": "搜索景点", "_mcp_service": "search",
         "input_schema": {"type": "object", "properties": {"city": {"type": "string"}, "category": {"type": "string"}}}},
        {"name": "search_restaurants", "description": "搜索美食", "_mcp_service": "search",
         "input_schema": {"type": "object", "properties": {"city": {"type": "string"}, "cuisine_type": {"type": "string"}}}},
        {"name": "get_travel_guide", "description": "旅游攻略", "_mcp_service": "search",
         "input_schema": {"type": "object", "properties": {"destination": {"type": "string"}, "duration": {"type": "integer"}}}},
    ],
    "railway": [
        {"name": "query_trains", "description": "火车票查询 (搜索聚合)", "_mcp_service": "railway",
         "input_schema": {"type": "object", "properties": {"from": {"type": "string"}, "to": {"type": "string"}, "date": {"type": "string"}}}},
    ],
    "flight": [
        {"name": "query_flights", "description": "航班查询 (搜索聚合)", "_mcp_service": "flight",
         "input_schema": {"type": "object", "properties": {"from": {"type": "string"}, "to": {"type": "string"}, "date": {"type": "string"}}}},
    ],
    "hotel": [
        {"name": "search_hotels", "description": "酒店搜索 (搜索聚合+高德POI)", "_mcp_service": "hotel",
         "input_schema": {"type": "object", "properties": {"city": {"type": "string"}, "check_in": {"type": "string"}, "check_out": {"type": "string"}}}},
    ],
}


def _get_virtual_tools(service_name: str) -> List[Dict]:
    return _VIRTUAL_TOOLS.get(service_name, [])
