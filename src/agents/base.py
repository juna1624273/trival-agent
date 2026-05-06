"""Base Sub-Agent with ReAct (Think-Act-Observe) reasoning loop.

Each sub-agent:
- Has a system prompt describing its domain expertise
- Is bound to a set of MCP tools
- Runs a Think-Act-Observe cycle within the execute phase
- Reports completion status via ReActTrace
"""

import json
import logging
from typing import List, Dict, Any, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

from src.graph.state import PlanStep, ReActTrace
from src.memory.cache_coordinator import SmartCacheCoordinator
from src.mcp.client_manager import McpClientManager
from src.llm.provider import create_execution_llm
from src.config.settings import settings
from src.utils.json_parser import extract_json

logger = logging.getLogger(__name__)


class BaseSubAgent:
    """ReAct agent bound to specific MCP tools for travel planning tasks."""

    agent_type: str = "base"
    system_prompt: str = "You are a helpful assistant."
    llm: Optional[BaseChatModel] = None
    tools: List[BaseTool] = []
    mcp_manager: Optional[McpClientManager] = None
    cache_coordinator: Optional[SmartCacheCoordinator] = None
    max_react_iterations: int = 5

    def __init__(
        self,
        agent_type: str,
        system_prompt: str,
        mcp_manager: Optional[McpClientManager] = None,
        cache_coordinator: Optional[SmartCacheCoordinator] = None,
        llm: Optional[BaseChatModel] = None,
        max_iterations: Optional[int] = None,
    ):
        self.agent_type = agent_type
        self.system_prompt = system_prompt
        self.mcp_manager = mcp_manager
        self.cache_coordinator = cache_coordinator
        self.llm = llm or create_execution_llm()
        self.max_react_iterations = max_iterations or settings.max_react_iterations
        self.tools = []

    async def initialize(self):
        """Initialize — load MCP tools from client manager."""
        if self.mcp_manager:
            # Get MCP tool definitions for this agent
            mcp_tools = await self.mcp_manager.get_agent_tools(self.agent_type)
            # Convert to LangChain tools
            from src.mcp.tool_adapter import create_langchain_tools
            from src.mcp.tool_registry import tool_registry

            for svc in self.mcp_manager.AGENT_SERVICE_MAP.get(self.agent_type, []):
                service_tools = await self.mcp_manager.get_tools(svc)
                if service_tools:
                    async def make_executor(svc_name):
                        async def executor(tool_name, args):
                            if self.cache_coordinator:
                                result, was_cached = await self.cache_coordinator.get_or_execute(
                                    tool_name=tool_name,
                                    tool_args=args,
                                    executor=lambda tn, ta: self.mcp_manager.call_tool(svc_name, tn, ta),
                                    service_name=svc_name,
                                )
                            else:
                                result = await self.mcp_manager.call_tool(svc_name, tool_name, args)
                            return result
                        return executor

                    executor = await make_executor(svc)
                    langchain_tools = create_langchain_tools(service_tools, svc, executor)
                    self.tools.extend(langchain_tools)
                    tool_registry.register_for_agent(self.agent_type, langchain_tools)

        logger.info(f"[{self.agent_type}] Agent initialized with {len(self.tools)} tools")

    async def invoke(
        self,
        plan_step: PlanStep,
        context: Dict[str, Any],
    ) -> ReActTrace:
        """Execute a plan step using the ReAct (Think-Act-Observe) loop.

        Args:
            plan_step: The step to execute
            context: Collected results from previous steps

        Returns:
            ReActTrace with thought/action/observation traces and completion flag
        """
        step_id = plan_step["step_id"]
        description = plan_step["description"]
        input_params = plan_step.get("input_params", {})
        expected_output = plan_step.get("expected_output", "")

        # Build the initial prompt
        context_str = json.dumps(context, ensure_ascii=False, indent=2) if context else "无"
        prompt = f"""任务步骤 #{step_id}: {description}

输入参数: {json.dumps(input_params, ensure_ascii=False)}
预期产出: {expected_output}

已收集的上下文信息:
{context_str}

请使用你的工具完成此步骤。你可以多轮调用工具，直到完成或无法继续。
完成时请输出包含 "complete": true 的 JSON。"""

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ]

        # ReAct loop
        traces: List[Dict[str, Any]] = []
        final_complete = False

        for iteration in range(self.max_react_iterations):
            logger.info(f"[{self.agent_type}] ReAct iteration {iteration + 1}/{self.max_react_iterations} for step #{step_id}")

            # THINK + ACT: Invoke LLM with tools
            llm_with_tools = self.llm.bind_tools(self.tools) if self.tools else self.llm
            try:
                response = await llm_with_tools.ainvoke(messages)
            except Exception as e:
                logger.error(f"[{self.agent_type}] LLM invocation failed: {e}")
                traces.append({
                    "thought": f"LLM调用失败: {e}",
                    "action": "error",
                    "observation": str(e),
                    "complete": True,
                })
                break

            messages.append(response)

            # Check if the LLM wants to call a tool
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    tool_name = tool_call.get("name", "unknown")
                    tool_args = tool_call.get("args", {})
                    tool_id = tool_call.get("id", "")

                    # OBSERVE: Execute the tool call
                    logger.info(f"[{self.agent_type}] Action: calling {tool_name}({tool_args})")
                    observation = await self._execute_tool(tool_name, tool_args)

                    # Record trace
                    traces.append({
                        "thought": response.content if isinstance(response.content, str) else str(response.content),
                        "action": f"{tool_name}({json.dumps(tool_args, ensure_ascii=False)})",
                        "observation": observation[:1000] if observation else "",
                    })

                    # Add tool result as ToolMessage
                    messages.append(ToolMessage(
                        content=observation or "工具执行完成",
                        tool_call_id=tool_id,
                    ))

                # Continue to next iteration — LLM will see tool results and naturally decide
                # whether to call more tools or output a completion response.
                continue
            else:
                # No tool call — LLM is giving a final answer, no forced eval needed
                content = response.content if isinstance(response.content, str) else str(response.content)
                try:
                    eval_data = extract_json(content)
                    if eval_data.get("complete"):
                        final_complete = True
                except json.JSONDecodeError:
                    pass

                if "complete" in content.lower() or "完成" in content:
                    final_complete = True

                traces.append({
                    "thought": content[:500],
                    "action": "complete" if final_complete else "final_response",
                    "observation": content[:500],
                })
                break

        # Build the final ReActTrace
        trace_summary = ReActTrace(
            step_id=step_id,
            thought="\n".join([t.get("thought", "") for t in traces]) if traces else "",
            action="\n".join([t.get("action", "") for t in traces]) if traces else "",
            observation="\n".join([t.get("observation", "") for t in traces]) if traces else "",
            complete=final_complete,
        )

        logger.info(f"[{self.agent_type}] Step #{step_id} done, complete={final_complete}, iterations={len(traces)}")
        return trace_summary

    async def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Optional[str]:
        """Execute a tool by name. Tries local tools first, then MCP."""
        # Try local LangChain tool first
        for tool in self.tools:
            if tool.name == tool_name:
                try:
                    result = await tool.ainvoke(tool_args)
                    return str(result) if result else None
                except Exception as e:
                    logger.error(f"Tool {tool_name} failed: {e}")
                    return f"工具执行错误: {str(e)}"

        # Try direct MCP call
        if self.mcp_manager:
            for svc in self.mcp_manager.AGENT_SERVICE_MAP.get(self.agent_type, []):
                try:
                    result = await self.mcp_manager.call_tool(svc, tool_name, tool_args)
                    return str(result) if result else None
                except Exception:
                    continue

        return f"错误: 未找到工具 {tool_name}"


class TransportAgent(BaseSubAgent):
    agent_type = "transport"
    system_prompt = """你是交通出行规划专家，可以使用铁路和航班查询工具。
查询机票和火车票时，请考虑：
- 直飞/直达优先，如没有则提供换乘方案
- 比较价格、时间、舒适度
- 标注退改签政策
- 如果用户未指定日期，默认查询最近一周
输出时以JSON格式组织数据。"""


class MapsAgent(BaseSubAgent):
    agent_type = "maps"
    system_prompt = """你是地图与路线规划专家，使用高德地图工具。
规划路线时考虑：
- 提供驾车、公交、步行多种方案
- 标注距离、预估时间、费用
- POI搜索时优先高评分结果
- 多个目的地时优化路线顺序
输出时以JSON格式组织数据。"""


class WeatherAgent(BaseSubAgent):
    agent_type = "weather"
    system_prompt = """你是天气预报专家，可以查询目的地天气。
查询天气时考虑：
- 提供未来7-15天的预报
- 标注温度和体感温度
- 降水概率 >50% 时给出带伞建议
- 极端天气（高温/台风/暴雨）给出警告
输出时以JSON格式组织数据。"""


class HotelAgent(BaseSubAgent):
    agent_type = "hotel"
    system_prompt = """你是酒店预订专家，可以搜索和比较酒店。
搜索酒店时考虑：
- 提供多个价位选项（经济/舒适/豪华）
- 标注距离主要交通枢纽和景点的距离
- 筛选含早、取消政策等条件
- 如用户未指定预算，提供各档位推荐
输出时以JSON格式组织数据。"""


class SearchAgent(BaseSubAgent):
    agent_type = "search"
    system_prompt = """你是旅游信息搜索专家，可以搜索景点、美食、攻略。
搜索信息时考虑：
- 搜索热门景点并标注评分和门票信息
- 搜索当地特色美食和推荐餐厅
- 提供实用的旅行贴士（交通卡、礼仪等）
- 标注信息的时效性和来源
输出时以JSON格式组织数据。"""


class FileAgent(BaseSubAgent):
    agent_type = "file"
    system_prompt = """你是文件操作专家，负责生成和导出旅行行程文件。
生成文件时考虑：
- 按日期和时间组织行程
- 包含必要的实用信息（地址、电话、预订号）
- PDF格式用于打印，Excel格式用于编辑
- 在文件名中包含日期和目的地信息
输出时以JSON格式组织数据。"""


# Agent factory
AGENT_MAP = {
    "transport": TransportAgent,
    "maps": MapsAgent,
    "weather": WeatherAgent,
    "hotel": HotelAgent,
    "search": SearchAgent,
    "file": FileAgent,
}


async def create_agent(
    agent_type: str,
    mcp_manager: Optional[McpClientManager] = None,
    cache_coordinator: Optional[SmartCacheCoordinator] = None,
    llm: Optional[BaseChatModel] = None,
) -> BaseSubAgent:
    """Factory function to create a sub-agent by type."""
    agent_cls = AGENT_MAP.get(agent_type)
    if not agent_cls:
        raise ValueError(f"Unknown agent type: {agent_type}")

    agent = agent_cls(
        agent_type=agent_type,
        system_prompt=agent_cls.system_prompt,
        mcp_manager=mcp_manager,
        cache_coordinator=cache_coordinator,
        llm=llm,
    )
    await agent.initialize()
    return agent
