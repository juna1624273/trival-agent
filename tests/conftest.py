"""Pytest fixtures for the travel planning agent tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock

pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
def mock_llm():
    """Mock LLM that returns a simple response."""
    from langchain_core.messages import AIMessage

    async def mock_ainvoke(messages, **kwargs):
        return AIMessage(content='{"complete": true, "thought": "测试完成"}')

    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=mock_ainvoke)
    llm.bind_tools = MagicMock(return_value=llm)
    return llm


@pytest.fixture
def mock_mcp_manager():
    """Mock MCP client manager."""
    manager = MagicMock()
    manager.get_agent_tools = AsyncMock(return_value=[])
    manager.get_tools = AsyncMock(return_value=[])
    manager.call_tool = AsyncMock(return_value={"result": "test"})
    manager.connect = AsyncMock(return_value=True)
    manager.connect_all = AsyncMock(return_value={"test": True})
    manager.disconnect = AsyncMock(return_value=None)
    manager.disconnect_all = AsyncMock(return_value=None)
    manager.AGENT_SERVICE_MAP = {
        "transport": ["railway", "flight"],
        "maps": ["amap"],
        "weather": ["weather"],
        "hotel": ["hotel"],
        "search": ["search"],
        "file": [],
    }
    return manager


@pytest.fixture
def sample_state():
    """Create a sample TravelAgentState for testing."""
    from src.graph.state import TravelAgentState, TravelPlan, PlanStep, create_initial_state

    return create_initial_state(
        user_query="帮我规划从北京到上海3日游",
        thread_id="test-thread-001",
        user_profile={"home_city": "北京", "budget_level": "comfort"},
    )


@pytest.fixture
def sample_plan():
    """Create a sample TravelPlan."""
    from src.graph.state import TravelPlan, PlanStep
    return TravelPlan(
        plan_id="test-plan-001",
        steps=[
            PlanStep(
                step_id=1,
                description="查询北京到上海的交通",
                agent_type="transport",
                input_params={"from": "北京", "to": "上海", "date": "2024-06-01"},
                expected_output="交通选项列表",
            ),
            PlanStep(
                step_id=2,
                description="查询上海天气",
                agent_type="weather",
                input_params={"city": "上海"},
                expected_output="天气预报",
            ),
        ],
        constraints={"budget": "中等", "departure_date": "2024-06-01"},
        generated_at="2024-01-01T00:00:00",
    )
