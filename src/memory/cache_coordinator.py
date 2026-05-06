"""Smart Cache Coordinator.

RAG-based caching for MCP tool results:
1. Exact-match check (in-memory dict, optionally Redis)
2. Semantic similarity search via vector store
3. On miss: execute tool, store result in both caches
"""

import hashlib
import json
import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple

from src.config.settings import settings
from src.memory.vector_store import VectorStore

logger = logging.getLogger(__name__)


class SmartCacheCoordinator:
    """Coordinates caching of MCP tool results with exact + semantic matching.

    Flow:
        1. Hash (tool_name, args) for exact-match lookup
        2. On miss, embed query and search vector store (semantic match)
        3. If similarity > threshold, reuse cached result
        4. Otherwise call MCP tool and cache the result
    """

    def __init__(
        self,
        vector_store: VectorStore,
        similarity_threshold: Optional[float] = None,
    ):
        self._vector_store = vector_store
        self._similarity_threshold = similarity_threshold or settings.cache_similarity_threshold
        self._exact_cache: Dict[str, Tuple[float, Any]] = {}  # key -> (expiry_ts, result)

        # TTL mapping per tool category
        self._ttl_map = {
            "weather": settings.cache_ttl_weather,
            "hotel": settings.cache_ttl_hotel,
            "transport": settings.cache_ttl_transport,
            "flight": settings.cache_ttl_transport,
            "railway": settings.cache_ttl_transport,
            "search": settings.cache_ttl_search,
            "amap": settings.cache_ttl_search,
            "maps": settings.cache_ttl_search,
        }

    def _make_cache_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Create a deterministic hash key from tool name and sorted args."""
        arg_str = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        combined = f"{tool_name}:{arg_str}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def _get_ttl(self, service_name: str) -> int:
        """Get TTL in minutes for a service."""
        for key, ttl in self._ttl_map.items():
            if key in service_name.lower():
                return ttl
        return 60  # default 1 hour

    def _build_query_text(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Build a searchable query text from tool name and arguments."""
        parts = [tool_name]
        for k, v in sorted(args.items()):
            parts.append(f"{k}:{v}")
        return " | ".join(parts)

    async def get_or_execute(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        executor: Callable[..., Any],
        service_name: str = "",
        ttl_minutes: Optional[int] = None,
    ) -> Tuple[Any, bool]:
        """Get cached result or execute the tool.

        Args:
            tool_name: Name of the MCP tool
            tool_args: Arguments for the tool call
            executor: Async callable that executes the actual MCP tool call
            service_name: MCP service name (for TTL lookup)
            ttl_minutes: Override TTL

        Returns:
            Tuple of (result, was_cached: bool)
        """
        if ttl_minutes is None:
            ttl_minutes = self._get_ttl(service_name)

        # Step 1: Exact-match cache lookup
        cache_key = self._make_cache_key(tool_name, tool_args)
        if cache_key in self._exact_cache:
            expiry, result = self._exact_cache[cache_key]
            if time.time() < expiry:
                logger.info(f"Exact cache HIT: {tool_name}")
                return result, True
            else:
                del self._exact_cache[cache_key]

        # Step 2: Semantic similarity search
        query_text = self._build_query_text(tool_name, tool_args)
        similar_entries = self._vector_store.search(
            query=query_text,
            tool_name=tool_name,
            k=1,
        )
        if similar_entries:
            entry = similar_entries[0]
            distance = entry.distance
            similarity = 1.0 - distance
            if similarity >= self._similarity_threshold:
                logger.info(f"Semantic cache HIT for {tool_name} (similarity={similarity:.3f})")
                return entry.result, True
            logger.info(f"Semantic cache MISS for {tool_name} (similarity={similarity:.3f} < {self._similarity_threshold})")

        # Step 3: Cache miss — execute the tool
        logger.info(f"Cache MISS for {tool_name}, executing MCP call")
        try:
            result = await executor(tool_name, tool_args)
        except Exception as e:
            logger.error(f"MCP execution failed for {tool_name}: {e}")
            raise

        # Step 4: Store result in both caches
        # Exact-match cache
        expiry = time.time() + ttl_minutes * 60
        self._exact_cache[cache_key] = (expiry, result)

        # Vector store cache
        try:
            result_dict = self._serialize_result(result)
            self._vector_store.store(
                tool_name=tool_name,
                query_text=query_text,
                result=result_dict,
                ttl_minutes=ttl_minutes,
            )
        except Exception as e:
            logger.warning(f"Failed to store result in vector cache: {e}")

        return result, False

    def _serialize_result(self, result: Any) -> Dict[str, Any]:
        """Convert tool result to a serializable dict."""
        if isinstance(result, dict):
            return result
        if isinstance(result, str):
            return {"result": result}
        if hasattr(result, 'content'):
            # MCP CallToolResult
            contents = []
            for c in result.content:
                if hasattr(c, 'text'):
                    contents.append({"type": "text", "text": c.text})
                elif hasattr(c, 'data'):
                    contents.append({"type": "data", "data": str(c.data)})
            return {"contents": contents}
        return {"result": str(result)}

    def clear_exact_cache(self):
        """Clear the in-memory exact-match cache."""
        self._exact_cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """Get basic cache statistics."""
        now = time.time()
        active = sum(1 for _, (exp, _) in self._exact_cache.items() if now < exp)
        return {
            "exact_cache_entries": len(self._exact_cache),
            "active_entries": active,
        }
