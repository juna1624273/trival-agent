"""Conditional edge routing for the travel planning StateGraph."""

from typing import Literal
from src.graph.state import TravelAgentState


def route_after_execute(state: TravelAgentState) -> Literal["replan", "human_input", "finalize"]:
    """Route after batch execution of plan steps.

    Returns:
        - "replan": Some steps remain, evaluate batch results
        - "human_input": Too many errors, need user intervention
        - "finalize": All steps complete
    """
    if state.get("needs_human"):
        return "human_input"

    travel_plan = state.get("travel_plan")
    if not travel_plan:
        return "human_input"

    completed_ids = state.get("completed_step_ids", [])
    total_steps = len(travel_plan.get("steps", []))

    if len(completed_ids) >= total_steps:
        return "finalize"

    error_count = state.get("error_count", 0)
    if error_count > 3:
        return "human_input"

    # After each batch, go through replan to assess results
    return "replan"


def route_after_replan(state: TravelAgentState) -> Literal["execute", "human_input", "finalize", "__end__"]:
    """Route after plan evaluation.

    Returns:
        - "execute": Continue with remaining steps
        - "human_input": Need user input
        - "finalize": All done, generate itinerary
        - "__end__": Terminate the workflow
    """
    phase = state.get("current_phase", "finalize")

    if state.get("needs_human"):
        return "human_input"

    if phase == "done":
        return "__end__"

    if phase == "finalize":
        return "finalize"

    if phase == "execute":
        travel_plan = state.get("travel_plan")
        if travel_plan:
            completed_ids = state.get("completed_step_ids", [])
            if len(completed_ids) < len(travel_plan.get("steps", [])):
                return "execute"
        return "finalize"

    return "finalize"


def route_after_plan(state: TravelAgentState) -> Literal["execute", "human_input"]:
    """Route after initial plan generation.

    Returns:
        - "execute": Plan ready, start execution
        - "human_input": Critical info missing
    """
    if state.get("needs_human"):
        return "human_input"
    return "execute"


def route_after_human(state: TravelAgentState) -> Literal["replan", "execute"]:
    """Route after receiving human input.

    Returns:
        - "replan": Re-evaluate plan with new info
        - "execute": Continue execution directly (fallback after too many rounds)
    """
    human_history = state.get("human_history", [])
    if len(human_history) >= 5:
        return "execute"
    return "replan"
