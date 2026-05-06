from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


# ============================================================
# Request Schemas
# ============================================================

class UserProfile(BaseModel):
    """User preferences and saved information."""
    home_city: Optional[str] = None
    preferred_transport: Optional[List[str]] = None  # ["flight", "train", "car"]
    budget_level: Optional[str] = None  # "budget" | "comfort" | "luxury"
    hotel_preferences: Optional[List[str]] = None  # ["near_subway", "breakfast", "quiet"]
    dietary_restrictions: Optional[List[str]] = None
    frequent_traveler_numbers: Optional[Dict[str, str]] = None
    language: Optional[str] = "zh-CN"


class PlanRequest(BaseModel):
    """Request to start a new travel planning session."""
    query: str = Field(..., description="Natural language travel request", min_length=5)
    profile: Optional[UserProfile] = None
    model: Optional[str] = Field(None, description="Model preset key (e.g. deepseek-chat, qwen-plus)")


class ResumeRequest(BaseModel):
    """Resume a plan after human interruption."""
    response: str = Field(..., description="User's answer to the system's question", min_length=1)


class FeedbackRequest(BaseModel):
    """Provide feedback for incremental plan adjustment."""
    feedback: str = Field(..., description="User feedback on the current plan", min_length=3)
    target_steps: Optional[List[int]] = Field(None, description="Specific step IDs to adjust, omit for full replan")


# ============================================================
# Response Schemas
# ============================================================

class PlanStepResponse(BaseModel):
    step_id: int
    description: str
    agent_type: str
    status: str = "pending"  # pending | running | completed | failed


class TravelPlanResponse(BaseModel):
    plan_id: str
    steps: List[PlanStepResponse]
    constraints: Dict[str, Any]


class HumanQuestionEvent(BaseModel):
    type: str = "human_input_required"
    question: str
    missing_fields: List[str]
    context: str
    history: List[Dict[str, Any]]


class ReActStepEvent(BaseModel):
    type: str = "react_step"
    step_id: int
    thought: str
    action: str
    observation: str
    complete: bool


class ProgressEvent(BaseModel):
    type: str  # "phase_change" | "step_complete" | "error" | "cache_hit"
    message: str
    data: Optional[Dict[str, Any]] = None


class PlanResponse(BaseModel):
    thread_id: str
    phase: str
    travel_plan: Optional[TravelPlanResponse] = None
    final_itinerary: Optional[Dict[str, Any]] = None
    needs_human: bool = False
    human_question: Optional[HumanQuestionEvent] = None
    react_traces: Optional[List[Dict[str, Any]]] = None
    artifacts: Optional[List[str]] = None


class StatusResponse(BaseModel):
    thread_id: str
    phase: str
    current_step: Optional[int] = None
    total_steps: Optional[int] = None
    completed_steps: Optional[int] = None
    needs_human: bool = False


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    thread_id: Optional[str] = None
