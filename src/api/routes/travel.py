"""FastAPI routes for travel planning.

Endpoints:
- POST /plan — start a new planning session
- GET /plan/{thread_id}/stream — SSE streaming of progress
- GET /plan/{thread_id}/status — check plan status
- POST /plan/{thread_id}/resume — resume after human interruption
"""

import json
import logging
import uuid
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
from langgraph.types import Command

from src.api.schemas import (
    PlanRequest,
    PlanResponse,
    ResumeRequest,
    StatusResponse,
)
from src.api.deps import get_agents, get_context_manager
from src.graph.builder import build_graph
from src.graph.state import create_initial_state
from src.interaction.human_loop import HumanLoopManager
from src.config.settings import settings, get_available_models
from src.utils.pdf_generator import generate_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["travel"])

# Hold compiled graph instance
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


@router.post("/plan", response_model=PlanResponse)
async def create_plan(request: PlanRequest):
    """Start a new travel planning session.

    Creates a new thread, initializes state, and executes the plan
    graph until completion or human interruption.
    """
    thread_id = str(uuid.uuid4())[:12]
    model = request.model or ""
    config = {
        "configurable": {
            "thread_id": thread_id,
            "agents": await get_agents(model),
        }
    }

    initial_state = create_initial_state(
        user_query=request.query,
        thread_id=thread_id,
        user_profile=request.profile.model_dump() if request.profile else None,
        llm_model=model,
    )

    graph = get_graph()
    try:
        result = await graph.ainvoke(initial_state, config)
        return _build_plan_response(thread_id, result)
    except Exception as e:
        logger.error(f"Plan creation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plan/{thread_id}/stream")
async def stream_plan(thread_id: str):
    """SSE streaming endpoint for real-time plan progress.

    Yields events as the graph processes each node:
    - phase_change: When graph transitions between phases
    - react_step: Each ReAct (Think-Act-Observe) cycle
    - human_input_required: When user input is needed
    - final: When the itinerary is complete
    """
    graph = get_graph()
    # Read the stored model from state so agents match user's selection
    try:
        existing = await graph.aget_state({"configurable": {"thread_id": thread_id}})
        llm_model = existing.values.get("llm_model", "") if existing and existing.values else ""
    except Exception:
        llm_model = ""

    config = {
        "configurable": {
            "thread_id": thread_id,
            "agents": await get_agents(llm_model),
        }
    }

    async def event_generator():
        try:
            async for event in graph.astream(None, config, stream_mode="updates"):
                # Compress messages if context manager is available
                yield f"data: {json.dumps(_format_stream_event(event), ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'thread_id': thread_id}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/plan/{thread_id}/status", response_model=StatusResponse)
async def get_plan_status(thread_id: str):
    """Get the current status of a planning session."""
    config = {"configurable": {"thread_id": thread_id}}
    graph = get_graph()

    try:
        state = await graph.aget_state(config)
        if state is None or not state.values:
            raise HTTPException(status_code=404, detail="Plan not found")

        values = state.values
        plan = values.get("travel_plan")
        return StatusResponse(
            thread_id=thread_id,
            phase=values.get("current_phase", "unknown"),
            current_step=values.get("current_step_index", 0),
            total_steps=len(plan["steps"]) if plan else 0,
            completed_steps=len(values.get("completed_step_ids", [])),
            needs_human=values.get("needs_human", False),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plan/{thread_id}/resume", response_model=PlanResponse)
async def resume_plan(thread_id: str, request: ResumeRequest):
    """Resume a plan that was paused for human input.

    Provides the user's response and continues graph execution.
    """
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    # Check if plan exists and is waiting for human input; also read model
    try:
        state = await graph.aget_state(config)
        if state is None or not state.values:
            raise HTTPException(status_code=404, detail="Plan not found")
        if not state.values.get("needs_human"):
            raise HTTPException(status_code=400, detail="Plan is not waiting for human input")
        llm_model = state.values.get("llm_model", "")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    config["configurable"]["agents"] = await get_agents(llm_model)

    try:
        # Resume with raw string so interrupt() returns clean user text
        result = await graph.ainvoke(
            Command(resume=request.response),
            config,
        )
        return _build_plan_response(thread_id, result)
    except Exception as e:
        logger.error(f"Resume failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models")
async def list_models():
    """List available LLM model presets."""
    return {"models": get_available_models(), "default": settings.llm_model}


@router.delete("/plan/{thread_id}")
async def cancel_plan(thread_id: str):
    """Cancel an ongoing planning session."""
    config = {"configurable": {"thread_id": thread_id}}
    # The MemorySaver checkpointer will naturally expire old data
    return {"status": "cancelled", "thread_id": thread_id}


@router.get("/plan/{thread_id}/export/pdf")
async def export_pdf(thread_id: str):
    """Export the final itinerary as a PDF file.

    Retrieves the graph state for the given thread and renders
    the itinerary as a styled PDF document with Chinese font support.
    """
    config = {"configurable": {"thread_id": thread_id}}
    graph = get_graph()

    try:
        state = await graph.aget_state(config)
        if state is None or not state.values:
            raise HTTPException(status_code=404, detail="Plan not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF export state fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    itinerary = state.values.get("final_itinerary")
    if not itinerary:
        raise HTTPException(
            status_code=400,
            detail="Itinerary not yet generated. Please wait for the plan to complete.",
        )

    try:
        pdf_buffer = await generate_pdf(itinerary, thread_id=thread_id)
        pdf_bytes = pdf_buffer.read()

        destination = ""
        if isinstance(itinerary, dict):
            overview = itinerary.get("overview", {})
            if isinstance(overview, dict):
                destination = overview.get("destination", "")
            if not destination:
                destination = itinerary.get("destination", itinerary.get("summary", ""))
        safe_dest = destination.replace("/", "_").replace("\\", "_") if destination else ""
        filename = f"旅行攻略_{safe_dest}_{thread_id}.pdf" if safe_dest else f"旅行攻略_{thread_id}.pdf"
        # RFC 5987: provide both filename* (encoded) and filename (raw) for broad browser compat
        encoded_filename = quote(filename, safe="")
        ascii_fallback = f"travel_plan_{thread_id}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=\"{ascii_fallback}\"; "
                    f"filename*=UTF-8''{encoded_filename}"
                ),
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")


def _build_plan_response(thread_id: str, state: dict) -> PlanResponse:
    """Build a PlanResponse from graph state."""
    plan = state.get("travel_plan")
    travel_plan_response = None
    if plan:
        from src.api.schemas import PlanStepResponse, TravelPlanResponse
        completed_ids = set(state.get("completed_step_ids", []))
        travel_plan_response = TravelPlanResponse(
            plan_id=plan["plan_id"],
            steps=[
                PlanStepResponse(
                    step_id=s["step_id"],
                    description=s["description"],
                    agent_type=s["agent_type"],
                    status="completed" if s["step_id"] in completed_ids else "pending",
                )
                for s in plan["steps"]
            ],
            constraints=plan.get("constraints", {}),
        )

    human_question = None
    if state.get("needs_human"):
        from src.api.schemas import HumanQuestionEvent
        human_question = HumanQuestionEvent(
            question=state.get("human_question", ""),
            missing_fields=state.get("missing_info_fields", []),
            context=json.dumps({"query": state.get("user_query", "")}, ensure_ascii=False),
            history=[{"question": h["question"], "response": h.get("response", "")}
                      for h in state.get("human_history", [])],
        )

    return PlanResponse(
        thread_id=thread_id,
        phase=state.get("current_phase", "unknown"),
        travel_plan=travel_plan_response,
        final_itinerary=state.get("final_itinerary"),
        needs_human=state.get("needs_human", False),
        human_question=human_question,
        react_traces=state.get("react_trace"),
        artifacts=state.get("artifacts"),
    )


def _format_stream_event(event) -> dict:
    """Format a graph update event for SSE streaming.

    Handles both plain dict events and namespace-wrapped tuples from
    LangGraph astream (stream_mode='updates' with subgraphs).
    Also guards against interrupt payloads that may be tuples/lists.
    """
    # LangGraph may wrap events as (namespace_tuple, data_dict)
    if isinstance(event, tuple):
        event = event[1] if len(event) > 1 and isinstance(event[1], dict) else {}

    if not isinstance(event, dict) or not event:
        return {"type": "node_update", "node": "unknown", "phase": "", "timestamp": ""}

    node_name = list(event.keys())[0]
    node_data = event.get(node_name, {})

    # Interrupt payloads may be tuples — extract the actual interrupt data
    if node_name == "__interrupt__":
        interrupt_data = node_data
        if isinstance(interrupt_data, (list, tuple)) and len(interrupt_data) > 0:
            interrupt_data = interrupt_data[0]
        question = ""
        missing_fields = []
        if isinstance(interrupt_data, dict):
            question = interrupt_data.get("question", "")
            missing_fields = interrupt_data.get("missing_fields", [])
        elif hasattr(interrupt_data, "value"):
            # LangGraph Interrupt object
            value = interrupt_data.value
            if isinstance(value, dict):
                question = value.get("question", "")
                missing_fields = value.get("missing_fields", [])
        return {
            "type": "human_input_required",
            "node": "human_input",
            "phase": "human_input",
            "timestamp": "",
            "data": {"question": question, "missing_fields": missing_fields},
        }

    if not isinstance(node_data, dict):
        return {"type": "node_update", "node": node_name, "phase": "", "timestamp": ""}

    base_event = {
        "type": "node_update",
        "node": node_name,
        "phase": node_data.get("current_phase", ""),
        "timestamp": "",
    }

    if node_name == "execute":
        traces = node_data.get("react_trace", [])
        if traces:
            base_event["type"] = "react_step"
            base_event["data"] = traces

    elif node_name == "human_input":
        base_event["type"] = "human_input_required"
        base_event["data"] = {
            "question": node_data.get("human_question", ""),
            "missing_fields": node_data.get("missing_info_fields", []),
        }

    elif node_name == "finalize":
        base_event["type"] = "finalize"
        base_event["data"] = {
            "itinerary": node_data.get("final_itinerary"),
        }

    elif node_name == "replan":
        base_event["type"] = "replan"
        base_event["data"] = {
            "phase": node_data.get("current_phase", ""),
            "needs_human": node_data.get("needs_human", False),
        }

    return base_event
