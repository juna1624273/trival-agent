from typing import Annotated, List, Optional, Dict, Any, Literal
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
import operator

from src.config.settings import settings


# ============================================================
# Structured sub-state models
# ============================================================

class PlanStep(TypedDict):
    step_id: int
    description: str
    agent_type: Literal["transport", "maps", "weather", "hotel", "search", "file"]
    input_params: Dict[str, Any]
    expected_output: str
    depends_on: List[int]  # step_ids this step depends on; [] for first step or independent steps


class TravelPlan(TypedDict):
    plan_id: str
    steps: List[PlanStep]
    constraints: Dict[str, Any]
    generated_at: str


class ReActTrace(TypedDict):
    step_id: int
    thought: str
    action: str
    observation: str
    complete: bool


class HumanInteraction(TypedDict):
    question: str
    response: Optional[str]
    timestamp: str
    context_snapshot: str


# ============================================================
# Reducer functions
# ============================================================

def merge_plans(left: Optional[TravelPlan], right: Optional[TravelPlan]) -> Optional[TravelPlan]:
    """Replace plan on replan; None means no change."""
    return right if right is not None else left


def append_react_trace(left: List[ReActTrace], right: List[ReActTrace]) -> List[ReActTrace]:
    """Accumulate ReAct traces across execution cycles."""
    if left is None:
        left = []
    if right is None:
        right = []
    return left + right


def append_tool_results(left: List[Dict], right: List[Dict]) -> List[Dict]:
    if left is None:
        left = []
    if right is None:
        right = []
    return left + right


def append_human_history(left: List[HumanInteraction], right: List[HumanInteraction]) -> List[HumanInteraction]:
    if left is None:
        left = []
    if right is None:
        right = []
    return left + right


def append_artifacts(left: List[str], right: List[str]) -> List[str]:
    if left is None:
        left = []
    if right is None:
        right = []
    return left + right


def append_int_list(left: List[int], right: List[int]) -> List[int]:
    """Append reducer for completed_step_ids. Safe for parallel writes."""
    if left is None:
        left = []
    if right is None:
        right = []
    return left + right


# ============================================================
# Main TravelAgentState
# ============================================================

class TravelAgentState(TypedDict):
    # User Input
    user_query: str
    user_profile: Dict[str, Any]

    # Messages (LangGraph-managed)
    messages: Annotated[List[BaseMessage], add_messages]

    # Phase tracking
    current_phase: Literal["plan", "execute", "replan", "human_input", "finalize", "done"]

    # Plan
    travel_plan: Annotated[Optional[TravelPlan], merge_plans]
    plan_history: Annotated[List[TravelPlan], operator.add]

    # Execute (ReAct)
    current_step_index: int
    completed_step_ids: Annotated[List[int], append_int_list]
    react_trace: Annotated[List[ReActTrace], append_react_trace]
    react_iteration_count: int
    tool_results: Annotated[List[Dict[str, Any]], append_tool_results]

    # Human-in-the-Loop
    needs_human: bool
    human_question: str
    human_history: Annotated[List[HumanInteraction], append_human_history]
    missing_info_fields: List[str]

    # Feedback Adjustment
    user_feedback: Optional[str]
    feedback_target_steps: Optional[List[int]]
    preserved_results: Optional[Dict[int, Dict]]

    # Final Output
    final_itinerary: Optional[Dict[str, Any]]
    artifacts: Annotated[List[str], append_artifacts]

    # Session
    thread_id: str
    error_count: int
    llm_model: str


# ============================================================
# Default initial state factory
# ============================================================

def create_initial_state(user_query: str, thread_id: str, user_profile: Optional[Dict] = None, llm_model: str = "") -> TravelAgentState:
    return TravelAgentState(
        user_query=user_query,
        user_profile=user_profile or {},
        messages=[],
        current_phase="plan",
        travel_plan=None,
        plan_history=[],
        current_step_index=0,
        completed_step_ids=[],
        react_trace=[],
        react_iteration_count=0,
        tool_results=[],
        needs_human=False,
        human_question="",
        human_history=[],
        missing_info_fields=[],
        user_feedback=None,
        feedback_target_steps=None,
        preserved_results=None,
        final_itinerary=None,
        artifacts=[],
        thread_id=thread_id,
        error_count=0,
        llm_model=llm_model or settings.llm_model,
    )
