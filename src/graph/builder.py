"""StateGraph Builder — constructs the full Plan-Execute-Replan workflow."""

import logging
from typing import Optional

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from src.graph.state import TravelAgentState
from src.graph.nodes.plan_node import plan_node
from src.graph.nodes.execute_node import execute_node
from src.graph.nodes.replan_node import replan_node
from src.graph.nodes.human_node import human_node
from src.graph.nodes.finalize_node import finalize_node
from src.graph.conditions import (
    route_after_execute,
    route_after_replan,
    route_after_plan,
    route_after_human,
)

logger = logging.getLogger(__name__)


def build_graph(
    checkpointer: Optional[BaseCheckpointSaver] = None,
    store: Optional[BaseStore] = None,
) -> StateGraph:
    """Build the complete travel planning StateGraph.

    Graph structure:
        START -> plan -> execute -> replan -> finalize -> END
                        ^              |  ^       |
                        |              v  |       |
                        |         human_input    |
                        |______________|_________|

    Flow:
        1. plan: Decompose user query into TravelPlan with dependency annotations
        2. execute: Run all ready steps (dependencies satisfied) in parallel via asyncio.gather
        3. replan: Evaluate batch results, detect gaps, adjust plan
        4. human_input: Pause for user input (if info missing)
        5. finalize: Synthesize final itinerary
    """
    workflow = StateGraph(TravelAgentState)

    # Add nodes
    workflow.add_node("plan", plan_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("replan", replan_node)
    workflow.add_node("human_input", human_node)
    workflow.add_node("finalize", finalize_node)

    # Entry edge
    workflow.add_edge(START, "plan")

    # Plan -> conditional routing
    workflow.add_conditional_edges(
        "plan",
        route_after_plan,
        {
            "execute": "execute",
            "human_input": "human_input",
        },
    )

    # Execute -> conditional routing (batch execution, no self-loop)
    workflow.add_conditional_edges(
        "execute",
        route_after_execute,
        {
            "replan": "replan",
            "human_input": "human_input",
            "finalize": "finalize",
        },
    )

    # Replan -> conditional routing
    workflow.add_conditional_edges(
        "replan",
        route_after_replan,
        {
            "execute": "execute",
            "human_input": "human_input",
            "finalize": "finalize",
            "__end__": END,
        },
    )

    # Human input -> replan (re-evaluate after user input)
    workflow.add_conditional_edges(
        "human_input",
        route_after_human,
        {
            "replan": "replan",
            "execute": "execute",
        },
    )

    # Finalize -> END
    workflow.add_edge("finalize", END)

    # Compile with checkpointer for persistence and interrupt support.
    # interrupt() is called inside human_node itself — no interrupt_before needed,
    # otherwise the double-interrupt prevents the node's return dict from being saved.
    compiled = workflow.compile(
        checkpointer=checkpointer or MemorySaver(),
        store=store,
    )

    logger.info("StateGraph compiled successfully")
    return compiled
