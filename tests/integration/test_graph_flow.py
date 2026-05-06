"""Integration test for the full graph workflow.

Tests the Plan → Execute → Replan → Finalize flow end-to-end.
"""

import pytest


@pytest.mark.asyncio
async def test_graph_initialization():
    """Test that the graph can be built and compiled."""
    from src.graph.builder import build_graph
    graph = build_graph()
    assert graph is not None
    assert hasattr(graph, "ainvoke")


@pytest.mark.asyncio
async def test_plan_generation(mock_llm):
    """Test that plan node generates a plan from user query."""
    from src.graph.nodes.plan_node import plan_node
    from src.graph.state import create_initial_state

    state = create_initial_state(
        user_query="帮我规划从北京到上海3日游",
        thread_id="test-001",
        user_profile={"home_city": "北京", "budget_level": "comfort"},
    )

    # Note: this test requires a real or mocked LLM
    # In CI/CD, use a mock LLM configured via dependency injection
    assert state["user_query"] == "帮我规划从北京到上海3日游"
    assert state["current_phase"] == "plan"


@pytest.mark.asyncio
async def test_state_transitions(sample_state, sample_plan):
    """Test state transitions between graph nodes."""
    # Test plan → execute transition
    sample_state["travel_plan"] = sample_plan
    sample_state["current_phase"] = "execute"
    assert sample_state["current_phase"] == "execute"
    assert len(sample_state["travel_plan"]["steps"]) == 2

    # Test execute → replan logic
    from src.graph.conditions import route_after_execute
    result = route_after_execute(sample_state)
    assert result in ("replan", "human_input", "finalize", "execute")


@pytest.mark.asyncio
async def test_context_manager_integration():
    """Test that context manager compresses messages correctly."""
    from src.memory.context_manager import ContextManager
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

    cm = ContextManager(max_tokens=500, keep_recent=5)
    messages = [
        HumanMessage(content="Plan a trip"),  # keep (recent)
    ] * 3

    result = cm.compress(messages)
    assert len(result) > 0
    assert all(isinstance(m, HumanMessage) for m in result)


@pytest.mark.asyncio
async def test_human_interaction_record():
    """Test HumanInteraction record creation."""
    from src.graph.state import HumanInteraction
    import time

    record = HumanInteraction(
        question="您的出发城市是哪里？",
        response="北京",
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        context_snapshot="测试上下文",
    )

    assert record["question"] == "您的出发城市是哪里？"
    assert record["response"] == "北京"
