"""FastAPI dependencies — provides shared resources via dependency injection."""

import logging
from typing import Optional

from src.config.settings import settings
from src.mcp.client_manager import McpClientManager
from src.memory.vector_store import VectorStore
from src.memory.cache_coordinator import SmartCacheCoordinator
from src.memory.context_manager import ContextManager
from src.agents.base import create_agent, BaseSubAgent
from src.llm.provider import create_llm

logger = logging.getLogger(__name__)

# Module-level singletons (initialized lazily at startup)
_mcp_manager: Optional[McpClientManager] = None
_cache_coordinator: Optional[SmartCacheCoordinator] = None
_context_manager: Optional[ContextManager] = None
_vector_store: Optional[VectorStore] = None
_agents: Optional[dict] = None


def get_mcp_manager() -> McpClientManager:
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = McpClientManager()
    return _mcp_manager


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore(persist_dir=settings.chroma_persist_dir)
    return _vector_store


def get_cache_coordinator() -> SmartCacheCoordinator:
    global _cache_coordinator
    if _cache_coordinator is None:
        _cache_coordinator = SmartCacheCoordinator(
            vector_store=get_vector_store(),
            similarity_threshold=settings.cache_similarity_threshold,
        )
    return _cache_coordinator


def get_context_manager() -> ContextManager:
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager(
            model_name=settings.llm_model,
            max_tokens=settings.max_context_tokens,
            keep_recent=settings.keep_recent_messages,
        )
    return _context_manager


async def get_agents(model: str = "") -> dict:
    """Get or initialize all sub-agents. Optionally specify a model preset."""
    global _agents
    model = model or settings.llm_model
    cache_key = f"agents_{model}"

    # Return cached agents if model hasn't changed
    if _agents is not None and getattr(get_agents, "_cache_key", "") == cache_key:
        return _agents

    mcp_manager = get_mcp_manager()
    cache_coord = get_cache_coordinator()
    llm = create_llm(model=model)

    _agents = {}
    agent_types = ["transport", "maps", "weather", "hotel", "search", "file"]
    for agent_type in agent_types:
        try:
            agent = await create_agent(
                agent_type=agent_type,
                mcp_manager=mcp_manager,
                cache_coordinator=cache_coord,
                llm=llm,
            )
            _agents[agent_type] = agent
            logger.info(f"Agent '{agent_type}' initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize agent '{agent_type}': {e}")
            from src.agents.base import BaseSubAgent, AGENT_MAP
            agent_cls = AGENT_MAP.get(agent_type, BaseSubAgent)
            _agents[agent_type] = agent_cls(
                agent_type=agent_type,
                system_prompt=agent_cls.system_prompt,
                llm=llm,
            )

    get_agents._cache_key = cache_key
    return _agents



async def initialize_services():
    """Initialize all services at application startup.

    MCP connections are tried but failures do NOT block startup.
    Vector store and agents initialize regardless of MCP availability.
    """
    logger.info("Initializing services...")

    # MCP connections — fire and forget, don't block startup
    try:
        mcp = get_mcp_manager()
        # Run with a short global timeout so startup isn't delayed
        results = await mcp.connect_all()
        for name, success in results.items():
            status = "connected" if success else "unavailable"
            logger.info(f"  MCP {name}: {status}")
    except Exception as e:
        logger.warning(f"MCP init skipped (non-blocking): {e}")

    # Initialize vector store — always works, no external dependency
    vs = get_vector_store()
    logger.info(f"  Vector store: ready ({settings.chroma_persist_dir})")

    # Initialize agents
    agents = await get_agents()
    logger.info(f"  Agents: {len(agents)} ready")

    logger.info("Services initialized")


async def shutdown_services():
    """Shutdown all services gracefully."""
    logger.info("Shutting down services...")

    global _mcp_manager
    if _mcp_manager:
        await _mcp_manager.disconnect_all()
        _mcp_manager = None

    global _vector_store
    if _vector_store:
        _vector_store.close()
        _vector_store = None

    logger.info("Services shut down")
