"""Plan Node — Phase 1: Decompose user request into structured TravelPlan."""

import json
import logging
import time
import uuid
from typing import Dict, Any
from langgraph.types import RunnableConfig

from src.graph.state import TravelAgentState, TravelPlan, PlanStep
from src.llm.provider import create_planning_llm
from src.llm.prompts.plan_prompt import PLAN_SYSTEM_PROMPT, PLAN_USER_TEMPLATE
from src.utils.json_parser import extract_json as _extract_json

logger = logging.getLogger(__name__)


async def plan_node(state: TravelAgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Generate a structured travel plan from user query.

    Uses the planning LLM to decompose the user's travel request into
    an ordered list of PlanStep objects, each assigned to a specific sub-agent.
    """
    logger.info(f"[Plan] Starting plan generation for thread {state.get('thread_id', 'unknown')}")

    llm = create_planning_llm(model=state.get("llm_model"))
    user_query = state["user_query"]
    user_profile = state.get("user_profile", {})

    # Build constraints text from user profile
    constraints_parts = []
    if user_profile:
        if user_profile.get("home_city"):
            constraints_parts.append(f"- 出发城市: {user_profile['home_city']}")
        if user_profile.get("budget_level"):
            constraints_parts.append(f"- 预算水平: {user_profile['budget_level']}")
        if user_profile.get("preferred_transport"):
            constraints_parts.append(f"- 偏好交通: {', '.join(user_profile['preferred_transport'])}")
        if user_profile.get("hotel_preferences"):
            constraints_parts.append(f"- 酒店偏好: {', '.join(user_profile['hotel_preferences'])}")
    constraints_text = "已知约束条件:\n" + "\n".join(constraints_parts) if constraints_parts else ""

    # Format the prompt
    user_prompt = PLAN_USER_TEMPLATE.format(
        user_query=user_query,
        user_profile=json.dumps(user_profile, ensure_ascii=False, indent=2),
        constraints_text=constraints_text,
    )

    try:
        response = await llm.ainvoke([
            {"role": "system", "content": PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])

        # Parse the structured JSON output
        plan_data = _extract_json(response.content)
        steps = [PlanStep(
            step_id=s["step_id"],
            description=s["description"],
            agent_type=s["agent_type"],
            input_params=s.get("input_params", {}),
            expected_output=s.get("expected_output", ""),
            depends_on=s.get("depends_on", []),
        ) for s in plan_data.get("steps", [])]

        # Normalize and validate dependencies
        steps = _normalize_dependencies(steps)

        travel_plan = TravelPlan(
            plan_id=plan_data.get("plan_id", f"plan_{uuid.uuid4().hex[:8]}"),
            steps=steps,
            constraints=plan_data.get("constraints", {}),
            generated_at=plan_data.get("generated_at", time.strftime("%Y-%m-%dT%H:%M:%S")),
        )

        logger.info(f"[Plan] Generated plan {travel_plan['plan_id']} with {len(travel_plan['steps'])} steps")

        # Check if human input is needed (missing critical info)
        needs_human = False
        missing_fields = plan_data.get("constraints", {}).get("missing_info", [])
        human_question = ""
        if missing_fields:
            missing_str = "、".join(missing_fields)
            human_question = f"为了给您制定更准确的旅行计划，请补充以下信息：{missing_str}"
            needs_human = True

        return {
            "travel_plan": travel_plan,
            "plan_history": [travel_plan],
            "current_phase": "human_input" if needs_human else "execute",
            "current_step_index": 0,
            "completed_step_ids": [],
            "needs_human": needs_human,
            "human_question": human_question,
            "missing_info_fields": missing_fields,
        }

    except Exception as e:
        logger.error(f"[Plan] Plan generation failed: {e}")
        return {
            "current_phase": "human_input",
            "needs_human": True,
            "human_question": "抱歉，我暂时无法理解您的需求。请更详细地描述您的旅行计划，包括目的地、出发城市、出行日期等。",
            "error_count": state.get("error_count", 0) + 1,
        }


def _normalize_dependencies(steps: list) -> list:
    """Fill default dependencies and validate.

    Rules:
    - Step 1: depends_on is always []
    - Empty depends_on for step N (N>1): defaults to [N-1] (sequential backward compat)
    - Validate: all deps reference valid step_ids < current step_id
    - Validate: no forward or self dependencies
    """
    if not steps:
        return steps

    valid_ids = {s["step_id"] for s in steps}
    for step in steps:
        sid = step["step_id"]
        deps = step.get("depends_on", [])
        if not deps and sid > 1:
            deps = [sid - 1]
        cleaned = []
        for d in deps:
            if d not in valid_ids:
                logger.warning(f"Step {sid}: invalid dependency {d}, ignoring")
            elif d >= sid:
                logger.warning(f"Step {sid}: dependency {d} >= step_id, ignoring (forward/circular)")
            else:
                cleaned.append(d)
        step["depends_on"] = cleaned
    return steps

