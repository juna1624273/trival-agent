"""Vector Store for semantic caching of MCP tool results."""

import json
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from chromadb import PersistentClient
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions

from src.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    id: str
    tool_name: str
    query_text: str
    result: Dict[str, Any]
    timestamp: float
    ttl_minutes: int
    distance: float = 1.0  # cosine distance from ChromaDB (0=identical, 1=unrelated)


class VectorStore:
    """ChromaDB-backed vector store for semantic similarity search on cached results."""

    COLLECTION_NAME = "mcp_tool_cache"

    def __init__(self, persist_dir: Optional[str] = None):
        self._persist_dir = persist_dir or settings.chroma_persist_dir
        self._client = PersistentClient(
            path=self._persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def search(self, query: str, tool_name: Optional[str] = None, k: int = 3) -> List[CacheEntry]:
        """Semantic search for cached results.

        Args:
            query: The natural language query to search for
            tool_name: Optional filter by tool name
            k: Number of results to return

        Returns:
            List of CacheEntry objects sorted by relevance
        """
        where_filter = {}
        if tool_name:
            where_filter = {"tool_name": tool_name}

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=k,
                where=where_filter if where_filter else None,
            )

            entries = []
            if results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    document = results["documents"][0][i] if results["documents"] else "{}"
                    distance = results["distances"][0][i] if results["distances"] else 0
                    try:
                        result_data = json.loads(document)
                    except json.JSONDecodeError:
                        result_data = {"raw": document}

                    entries.append(CacheEntry(
                        id=doc_id,
                        tool_name=metadata.get("tool_name", ""),
                        query_text=metadata.get("query_text", query),
                        result=result_data,
                        timestamp=float(metadata.get("timestamp", 0)),
                        ttl_minutes=int(metadata.get("ttl_minutes", 60)),
                        distance=float(distance) if distance else 1.0,
                    ))
            return entries
        except Exception as e:
            logger.warning(f"Vector search failed: {e}, returning empty")
            return []

    def store(self, tool_name: str, query_text: str, result: Dict[str, Any], ttl_minutes: int = 60):
        """Store a tool result in the vector store.

        Args:
            tool_name: Name of the MCP tool
            query_text: The query that produced this result (for semantic matching)
            result: The tool result data
            ttl_minutes: Time-to-live in minutes
        """
        import time
        import uuid
        doc_id = f"{tool_name}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        result_json = json.dumps(result, ensure_ascii=False, default=str)

        try:
            self._collection.add(
                ids=[doc_id],
                documents=[result_json],
                metadatas=[{
                    "tool_name": tool_name,
                    "query_text": query_text,
                    "timestamp": time.time(),
                    "ttl_minutes": ttl_minutes,
                }],
            )
        except Exception as e:
            logger.warning(f"Failed to store in vector DB: {e}")

    def delete_expired(self):
        """Remove expired cache entries based on TTL."""
        import time
        try:
            all_data = self._collection.get()
            if not all_data["ids"]:
                return
            expired_ids = []
            now = time.time()
            for i, doc_id in enumerate(all_data["ids"]):
                metadata = all_data["metadatas"][i] if all_data["metadatas"] else {}
                ts = float(metadata.get("timestamp", 0))
                ttl_minutes = int(metadata.get("ttl_minutes", 60))
                if now - ts > ttl_minutes * 60:
                    expired_ids.append(doc_id)
            if expired_ids:
                self._collection.delete(ids=expired_ids)
                logger.debug(f"Deleted {len(expired_ids)} expired cache entries")
        except Exception as e:
            logger.warning(f"Failed to clean expired cache entries: {e}")

    def close(self):
        """Close the persistent client."""
        pass  # PersistentClient doesn't require explicit close
