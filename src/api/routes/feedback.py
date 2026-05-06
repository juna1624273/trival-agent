"""FastAPI routes for feedback-based incremental plan adjustment."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from langgraph.types import Command

from src.api.schemas import FeedbackRequest, PlanResponse
from src.api.deps import get_agents
from src.graph.builder import build_graph
from src.utils.merge import smart_merge_plan, identify_affected_steps

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["feedback"])


def get_graph():
    from src.api.routes.travel import get_graph as _get_graph
    return _get_graph()


@router.post("/plan/{thread_id}/feedback", response_model=PlanResponse)
async def provide_feedback(thread_id: str, request: FeedbackRequest):
    """Submit feedback for incremental plan adjustment.

    Only regenerates the affected steps while preserving unadjusted parts.
    The system:
    1. Identifies which steps are affected by the feedback
    2. Preserves results from unaffected steps
    3. Re-executes only the affected steps
    4. Merges results intelligently
    """
    config = {
        "configurable": {
            "thread_id": thread_id,
            "agents": await get_agents(),
        }
    }

    graph = get_graph()

    try:
        # Check current state
        state = await graph.aget_state(config)
        if state is None or not state.values:
            raise HTTPException(status_code=404, detail="Plan not found")

        current_state = state.values
        current_plan = current_state.get("travel_plan")

        if not current_plan:
            raise HTTPException(status_code=400, detail="No plan to adjust")

        # Identify affected steps
        if request.target_steps:
            affected_step_ids = request.target_steps
        else:
            affected_step_ids = identify_affected_steps(current_plan, request.feedback)

        # Preserve results from unaffected steps
        preserved_results = {}
        for tr in current_state.get("tool_results", []):
            sid = tr.get("step_id")
            if sid not in affected_step_ids:
                preserved_results[sid] = tr

        # Resume the graph with feedback and preserved results
        result = await graph.ainvoke(
            Command(update={
                "user_feedback": request.feedback,
                "feedback_target_steps": affected_step_ids,
                "preserved_results": preserved_results,
                "current_phase": "replan",
            }),
            config,
        )

        return _build_feedback_response(thread_id, result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Feedback processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _build_feedback_response(thread_id: str, state: dict) -> PlanResponse:
    """Build PlanResponse from feedback-adjusted state."""
    from src.api.routes.travel import _build_plan_response
    return _build_plan_response(thread_id, state)
