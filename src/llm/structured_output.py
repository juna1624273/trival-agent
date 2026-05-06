"""Pydantic schemas for LLM structured output parsing."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class PlanStepOutput(BaseModel):
    """Structured output for a single plan step."""
    step_id: int
    description: str
    agent_type: str
    input_params: Dict[str, Any]
    expected_output: str


class TravelPlanOutput(BaseModel):
    """Structured output for the full travel plan."""
    plan_id: str
    steps: List[PlanStepOutput]
    constraints: Dict[str, Any]
    generated_at: str


class ReActEvaluation(BaseModel):
    """Structured output for ReAct step evaluation."""
    thought: str
    next_action: Optional[str] = None
    next_action_args: Optional[Dict[str, Any]] = None
    observation: str = ""
    complete: bool = False
    missing_info: List[str] = Field(default_factory=list)


class ReplanAssessment(BaseModel):
    """Structured output for replan evaluation."""
    assessment: str
    phase: str  # execute | human_input | finalize
    needs_human: bool = False
    human_question: str = ""
    missing_info_fields: List[str] = Field(default_factory=list)
    adjusted_steps: List[Dict[str, Any]] = Field(default_factory=list)
    adjusted_step_ids: List[int] = Field(default_factory=list)
    reason: str = ""


class HumanQuestion(BaseModel):
    """Structured output for human question generation."""
    question: str
    options: List[str] = Field(default_factory=list)
    required: bool = True


class HumanResponseExtraction(BaseModel):
    """Structured output for parsing user responses."""
    extracted_info: Dict[str, Any] = Field(default_factory=dict)
    confidence: str = "medium"  # high | medium | low
    need_followup: bool = False
    followup_question: str = ""


class FinalItinerary(BaseModel):
    """Structured output for the final travel itinerary."""
    overview: Dict[str, Any] = Field(default_factory=dict)
    transport: List[Dict[str, Any]] = Field(default_factory=list)
    hotels: List[Dict[str, Any]] = Field(default_factory=list)
    weather: List[Dict[str, Any]] = Field(default_factory=list)
    daily_schedule: List[Dict[str, Any]] = Field(default_factory=list)
    attractions: List[Dict[str, Any]] = Field(default_factory=list)
    restaurants: List[Dict[str, Any]] = Field(default_factory=list)
    tips: List[str] = Field(default_factory=list)
    budget_estimate: Dict[str, Any] = Field(default_factory=dict)
    generated_at: str = ""
    notes: List[str] = Field(default_factory=list)
