"""Human-in-the-Loop Node — Pause execution and wait for user input."""

import json
import logging
import time
from typing import Dict, Any

from langgraph.types import interrupt, RunnableConfig

from src.graph.state import TravelAgentState, HumanInteraction
from src.interaction.human_loop import HumanLoopManager
from src.llm.provider import create_planning_llm


logger = logging.getLogger(__name__)


async def human_node(state: TravelAgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Pause the graph and surface a question to the user.

    Uses LangGraph's interrupt() mechanism to pause execution.
    The graph waits until the user provides a response via Command(resume=...).
    """
    question = state.get("human_question", "")
    if not question:
        missing = state.get("missing_info_fields", [])
        if missing:
            missing_str = "、".join(missing)
            question = f"请补充以下信息以继续规划：{missing_str}"
        else:
            question = "请提供更多信息以继续规划。"

    human_history = state.get("human_history", [])
    current_plan = state.get("travel_plan")

    context_snapshot = json.dumps({
        "query": state.get("user_query", ""),
        "plan_steps_completed": len(state.get("tool_results", [])),
        "plan_steps_total": len(current_plan["steps"]) if current_plan else 0,
    }, ensure_ascii=False)

    logger.info(f"[Human] Interrupting for user input: {question}")

    interrupt_data = {
        "type": "human_input_required",
        "question": question,
        "missing_fields": state.get("missing_info_fields", []),
        "context": context_snapshot,
        "history": [{"question": h["question"], "response": h.get("response", "")}
                      for h in human_history],
    }

    user_response = interrupt(interrupt_data)

    interaction = HumanInteraction(
        question=question,
        response=user_response if isinstance(user_response, str) else str(user_response),
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        context_snapshot=context_snapshot,
    )

    logger.info(f"[Human] Received user response: {user_response}")

    # Parse user response and integrate extracted info into user_profile
    user_profile = state.get("user_profile", {})
    response_text = user_response if isinstance(user_response, str) else str(user_response)

    try:
        manager = HumanLoopManager(
            llm=create_planning_llm(model=state.get("llm_model"))
        )
        integrated = await manager.integrate_response(
            question=question,
            response_text=response_text,
            user_profile=user_profile,
        )
        updated_profile = integrated.get("updated_profile", user_profile)
        logger.info(f"[Human] Integrated response, updated profile: {updated_profile}")
    except Exception as e:
        logger.warning(f"[Human] Failed to integrate response: {e}")
        updated_profile = user_profile

    return {
        "human_history": [interaction],
        "needs_human": False,
        "current_phase": "replan",
        "human_question": "",
        "missing_info_fields": [],
        "user_profile": updated_profile,
    }
