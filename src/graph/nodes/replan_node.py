"""Replan Node — Phase 3: Evaluate results, detect gaps, adjust plan."""

import json
import logging
from typing import Dict, Any

from langgraph.types import RunnableConfig

from src.graph.state import TravelAgentState
from src.llm.provider import create_planning_llm
from src.llm.prompts.replan_prompt import REPLAN_SYSTEM_PROMPT, REPLAN_USER_TEMPLATE
from src.utils.json_parser import extract_json as _extract_json

logger = logging.getLogger(__name__)


async def replan_node(state: TravelAgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Evaluate execution results and decide next action.

    Three possible outcomes:
    1. CONTINUE — adjust remaining steps and go back to execute
    2. HUMAN — info gaps detected, need user input
    3. FINALIZE — all steps completed, generate final itinerary
    """
    logger.info(f"[Replan] Evaluating plan execution for thread {state.get('thread_id', 'unknown')}")

    travel_plan = state.get("travel_plan")
    if not travel_plan:
        return {"current_phase": "human_input", "needs_human": True,
                "human_question": "请提供您的旅行需求"}

    # Handle user feedback if present
    user_feedback = state.get("user_feedback")
    has_feedback = bool(user_feedback)

    # Build the replan prompt
    completed_ids = set(state.get("completed_step_ids", []))
    steps = travel_plan.get("steps", [])
    completed_results = [r for r in state.get("tool_results", [])]
    pending_steps = [s for s in steps if s["step_id"] not in completed_ids]

    feedback_section = ""
    if has_feedback:
        feedback_section = f"用户反馈:\n{user_feedback}\n\n请根据用户反馈调整相关步骤，保留用户未提及的部分不变。"

    # Build human interaction history for the prompt
    human_history = state.get("human_history", [])
    if human_history:
        history_lines = []
        for i, h in enumerate(human_history, 1):
            q = h.get("question", "")
            r = h.get("response", "等待回复...")
            history_lines.append(f"  第{i}轮: 系统问「{q}」→ 用户答「{r}」")
        human_history_text = "\n".join(history_lines)
    else:
        human_history_text = "（尚无交互记录）"

    user_prompt = REPLAN_USER_TEMPLATE.format(
        user_query=state.get("user_query", ""),
        human_history=human_history_text,
        current_plan=json.dumps(travel_plan, ensure_ascii=False, indent=2),
        completed_results=json.dumps(completed_results, ensure_ascii=False, indent=2),
        pending_steps=json.dumps(pending_steps, ensure_ascii=False, indent=2),
        feedback_section=feedback_section,
    )

    llm = create_planning_llm(model=state.get("llm_model"))
    try:
        response = await llm.ainvoke([
            {"role": "system", "content": REPLAN_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])

        assessment = _extract_json(response.content)
        logger.info(f"[Replan] Assessment: phase={assessment.get('phase')}, needs_human={assessment.get('needs_human')}")

        phase = assessment.get("phase", "finalize")
        needs_human = assessment.get("needs_human", False)

        result = {
            "current_phase": phase,
            "needs_human": needs_human,
            "human_question": assessment.get("human_question", ""),
            "missing_info_fields": assessment.get("missing_info_fields", []),
        }

        # If feedback was applied, clear it
        if has_feedback:
            result["user_feedback"] = None
            result["feedback_target_steps"] = None

        # If steps were adjusted, update the plan
        adjusted_steps = assessment.get("adjusted_steps", [])
        adjusted_step_ids = assessment.get("adjusted_step_ids", [])
        if adjusted_steps and adjusted_step_ids:
            # Merge adjusted steps into the plan
            new_steps = list(travel_plan["steps"])
            for adj_step in adjusted_steps:
                sid = adj_step.get("step_id")
                if sid is not None:
                    # Find and update
                    for i, s in enumerate(new_steps):
                        if s["step_id"] == sid:
                            new_steps[i] = adj_step
                            break
            updated_plan = {**travel_plan, "steps": new_steps}
            result["travel_plan"] = updated_plan

        return result

    except Exception as e:
        logger.error(f"[Replan] Failed: {e}", exc_info=True)
        # On error, try to proceed to finalize
        if len(completed_ids) >= len(steps):
            return {"current_phase": "finalize"}
        return {"current_phase": "human_input", "needs_human": True,
                "human_question": "规划评估中遇到问题，请检查您的需求是否清晰完整。"}

