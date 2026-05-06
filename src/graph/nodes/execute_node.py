"""Execute Node — Concurrent batch executor for plan steps.

Runs all "ready" steps (dependencies satisfied) in parallel via asyncio.gather.
Each step dispatches to its corresponding sub-agent, which runs its own ReAct loop.
"""

import asyncio
import logging
from typing import Dict, Any, List

from langgraph.types import RunnableConfig

from src.graph.state import TravelAgentState, PlanStep
from src.config.settings import settings

logger = logging.getLogger(__name__)


async def execute_node(state: TravelAgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Execute all ready plan steps in parallel via asyncio.gather.

    1. Find steps whose dependencies are all satisfied
    2. Run them concurrently
    3. Merge results and determine next phase
    """
    travel_plan = state.get("travel_plan")
    if not travel_plan:
        logger.warning("[Execute] No travel plan found in state")
        return {"current_phase": "human_input", "needs_human": True,
                "human_question": "计划生成失败，请重新描述您的需求。"}

    completed_ids = list(state.get("completed_step_ids", []))
    steps = travel_plan.get("steps", [])

    ready_steps = _get_ready_steps(steps, completed_ids)
    if not ready_steps:
        if len(set(completed_ids)) >= len(steps):
            logger.info("[Execute] All steps completed")
            return {"current_phase": "finalize"}
        else:
            logger.warning(f"[Execute] No ready steps but {len(completed_ids)}/{len(steps)} done — possible broken deps")
            return {"current_phase": "replan"}

    logger.info(f"[Execute] Batch executing {len(ready_steps)} steps: {[s['step_id'] for s in ready_steps]}")

    agents = config.get("configurable", {}).get("agents", {})

    # Build context from ONLY pre-batch completed steps (isolated from siblings)
    completed_before = set(completed_ids)
    base_context = _build_context_for_step(state, completed_before)

    # Run all ready steps in parallel
    tasks = []
    for step in ready_steps:
        agent = agents.get(step["agent_type"])
        if not agent:
            logger.warning(f"[Execute] Agent not found for type: {step['agent_type']}")
            tasks.append(_fake_error_task(step))
        else:
            tasks.append(_execute_single_step(step, agent, base_context))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Merge results
    combined: Dict[str, Any] = {
        "react_trace": [],
        "tool_results": [],
        "completed_step_ids": [],
        "error_count": state.get("error_count", 0),
        "react_iteration_count": state.get("react_iteration_count", 0),
    }

    any_incomplete = False
    batch_errors = 0

    for result in results:
        if isinstance(result, Exception):
            batch_errors += 1
            logger.error(f"[Execute] Unhandled exception in batch: {result}")
            continue
        combined["react_trace"].extend(result.get("react_trace", []))
        combined["tool_results"].extend(result.get("tool_results", []))
        combined["completed_step_ids"].extend(result.get("completed_step_ids", []))
        combined["error_count"] += result.get("error_count", 0)
        combined["react_iteration_count"] += result.get("react_iteration_count", 0)
        if not result.get("step_complete", True):
            any_incomplete = True
        if not result.get("step_success", True):
            batch_errors += 1

    # Determine next phase
    new_completed = completed_before | set(combined["completed_step_ids"])
    all_done = len(new_completed) >= len(steps)

    if combined["error_count"] > 3:
        combined["current_phase"] = "human_input"
        combined["needs_human"] = True
        combined["human_question"] = "执行过程中遇到多个错误，请检查需求或稍后重试。"
    elif all_done:
        combined["current_phase"] = "finalize"
        combined["needs_human"] = False
    elif any_incomplete:
        combined["current_phase"] = "replan"
        combined["needs_human"] = False
    else:
        combined["current_phase"] = "replan"
        combined["needs_human"] = False

    combined["current_step_index"] = len(new_completed)

    logger.info(f"[Execute] Batch complete: {len(ready_steps)} steps, "
                f"{len(new_completed)}/{len(steps)} total done, "
                f"errors={batch_errors}, phase={combined['current_phase']}")

    return combined


# ============================================================
# Helpers
# ============================================================

def _get_ready_steps(steps: List[PlanStep], completed_ids: List[int]) -> List[PlanStep]:
    """Return steps whose dependencies are all satisfied, up to max_parallel_steps."""
    completed = set(completed_ids)
    ready = []
    for step in steps:
        if step["step_id"] in completed:
            continue
        deps = step.get("depends_on", [])
        if all(d in completed for d in deps):
            ready.append(step)
    ready.sort(key=lambda s: len(s.get("depends_on", [])))
    return ready[:settings.max_parallel_steps]


def _build_context_for_step(state: TravelAgentState, completed_before_batch: set) -> Dict[str, Any]:
    """Build context from tool results completed before this batch only.

    Sibling steps in the same batch do NOT see each other's results.
    """
    tool_results = state.get("tool_results", [])
    context = {}
    for tr in tool_results:
        step_id = tr.get("step_id", -1)
        if step_id in completed_before_batch:
            key = f"step_{step_id}_{tr.get('agent_type', 'unknown')}"
            context[key] = {
                "description": tr.get("description", ""),
                "data": tr.get("observation", ""),
            }
    return context


async def _execute_single_step(
    step: PlanStep,
    agent,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute a single step via its sub-agent. Never raises — errors are in the return dict."""
    step_id = step["step_id"]
    agent_type = step["agent_type"]
    try:
        react_trace = await agent.invoke(step, context)

        return {
            "react_trace": [react_trace],
            "tool_results": [{
                "step_id": step_id,
                "agent_type": agent_type,
                "description": step["description"],
                "observation": react_trace["observation"],
                "complete": react_trace["complete"],
            }],
            "completed_step_ids": [step_id],
            "react_iteration_count": 1,
            "step_success": True,
            "step_complete": react_trace["complete"],
            "error_count": 0,
        }
    except Exception as e:
        logger.error(f"[Execute] Step #{step_id} ({agent_type}) failed: {e}", exc_info=True)
        return {
            "react_trace": [{
                "step_id": step_id,
                "thought": f"执行失败: {e}",
                "action": "error",
                "observation": str(e),
                "complete": False,
            }],
            "tool_results": [{
                "step_id": step_id,
                "agent_type": agent_type,
                "description": step["description"],
                "observation": f"Error: {e}",
                "complete": False,
            }],
            "completed_step_ids": [step_id],
            "react_iteration_count": 1,
            "step_success": False,
            "step_complete": False,
            "error_count": 1,
        }


async def _fake_error_task(step: PlanStep) -> Dict[str, Any]:
    """Return an error result when a sub-agent is not available."""
    return {
        "react_trace": [{
            "step_id": step["step_id"],
            "thought": "Agent not available",
            "action": "skip",
            "observation": f"Agent type '{step['agent_type']}' not found",
            "complete": False,
        }],
        "tool_results": [{
            "step_id": step["step_id"],
            "agent_type": step["agent_type"],
            "description": step["description"],
            "observation": "Agent not available",
            "complete": False,
        }],
        "completed_step_ids": [step["step_id"]],
        "react_iteration_count": 0,
        "step_success": False,
        "step_complete": False,
        "error_count": 1,
    }
