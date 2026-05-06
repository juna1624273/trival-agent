"""Smart merge utilities for incremental feedback adjustment.

Preserves unadjusted parts of the plan while updating only the affected steps.
"""

import time
import uuid
import logging
from typing import List, Optional, Dict, Any

from src.graph.state import TravelPlan, PlanStep

logger = logging.getLogger(__name__)


def smart_merge_plan(
    original_plan: TravelPlan,
    feedback: str,
    affected_step_ids: List[int],
    regenerated_steps: List[PlanStep],
) -> TravelPlan:
    """Incrementally update a travel plan based on user feedback.

    Only steps affected by the feedback are regenerated; all other steps
    are preserved as-is. This avoids costly full re-generation.

    Args:
        original_plan: The current travel plan
        feedback: User feedback text
        affected_step_ids: IDs of steps that need regeneration
        regenerated_steps: New versions of the affected steps

    Returns:
        Updated TravelPlan with merged steps
    """
    if not affected_step_ids:
        return original_plan

    # Build lookup of preserved steps
    preserved = {}
    for step in original_plan["steps"]:
        if step["step_id"] not in affected_step_ids:
            preserved[step["step_id"]] = step

    # Build lookup of regenerated steps
    regenerated = {}
    for step in regenerated_steps:
        regenerated[step["step_id"]] = step

    # Merge: preserved steps + regenerated steps
    all_step_ids = sorted(set(list(preserved.keys()) + list(regenerated.keys())))
    merged_steps = []
    seen_ids = set()

    for sid in all_step_ids:
        if sid in seen_ids:
            continue
        seen_ids.add(sid)

        if sid in regenerated:
            merged_steps.append(regenerated[sid])
        elif sid in preserved:
            merged_steps.append(preserved[sid])

    # Validate step ordering
    merged_steps.sort(key=lambda s: s["step_id"])

    # Generate new plan ID
    new_plan_id = f"plan_{uuid.uuid4().hex[:8]}"

    logger.info(f"Smart merge: preserved {len(preserved)} steps, "
                f"regenerated {len(regenerated)}, merged {len(merged_steps)}")

    return TravelPlan(
        plan_id=new_plan_id,
        steps=merged_steps,
        constraints=original_plan.get("constraints", {}),
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )


def identify_affected_steps(
    plan: TravelPlan,
    feedback: str,
) -> List[int]:
    """Simple heuristic to identify which steps are affected by feedback.

    In production, this would use an LLM to analyze the feedback against steps.
    This provides a keyword-based fallback.

    Args:
        plan: The travel plan
        feedback: User feedback text

    Returns:
        List of step IDs affected by the feedback
    """
    affect_keywords = {
        "transport": ["交通", "机票", "火车", "高铁", "航班", "出行方式", "大巴"],
        "hotel": ["酒店", "住宿", "宾馆", "民宿", "旅馆"],
        "weather": ["天气", "温度", "气候", "下雨"],
        "maps": ["路线", "地图", "导航", "距离", "周边"],
        "search": ["景点", "美食", "餐厅", "好玩", "好吃", "攻略", "打卡"],
    }

    affected_ids = []
    for step in plan["steps"]:
        agent_type = step.get("agent_type", "")
        keywords = affect_keywords.get(agent_type, [])
        for kw in keywords:
            if kw in feedback:
                affected_ids.append(step["step_id"])
                break

    if not affected_ids:
        # If no specific keywords, mark all unexecuted steps as affected
        affected_ids = [s["step_id"] for s in plan["steps"]]

    return affected_ids


def merge_tool_results(
    preserved: Dict[int, Dict],
    new_results: List[Dict],
) -> List[Dict]:
    """Merge preserved tool results with new results.

    Args:
        preserved: Existing results keyed by step_id
        new_results: New results to merge in

    Returns:
        Combined list of results
    """
    merged = list(preserved.values())
    for new_r in new_results:
        step_id = new_r.get("step_id")
        # Replace if exists, otherwise append
        replaced = False
        for i, existing in enumerate(merged):
            if existing.get("step_id") == step_id:
                merged[i] = new_r
                replaced = True
                break
        if not replaced:
            merged.append(new_r)
    return merged
