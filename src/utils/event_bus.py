"""Simple event bus for streaming progress events."""

import asyncio
import logging
from typing import Dict, Any, AsyncIterator

logger = logging.getLogger(__name__)


class EventBus:
    """Async event bus for publishing progress events to SSE subscribers.

    Each thread_id has its own queue of events. Subscribers can iterate
    over events as they arrive.
    """

    def __init__(self, max_queue_size: int = 1000):
        self._queues: Dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()
        self._max_queue_size = max_queue_size

    async def subscribe(self, thread_id: str) -> AsyncIterator[Dict[str, Any]]:
        """Subscribe to events for a thread. Yields events as they arrive."""
        queue = await self._get_or_create_queue(thread_id)
        try:
            while True:
                event = await queue.get()
                if event is None:  # Sentinel to close subscription
                    break
                yield event
        except asyncio.CancelledError:
            logger.debug(f"Subscription cancelled for {thread_id}")
        finally:
            await self._cleanup_queue(thread_id)

    async def publish(self, thread_id: str, event: Dict[str, Any]):
        """Publish an event to a thread's subscribers."""
        queue = await self._get_or_create_queue(thread_id)
        if queue.qsize() >= self._max_queue_size:
            logger.warning(f"Event queue full for {thread_id}, dropping oldest event")
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await queue.put(event)

    async def close_subscription(self, thread_id: str):
        """Close a subscription by sending a sentinel."""
        queue = await self._get_or_create_queue(thread_id)
        await queue.put(None)

    async def _get_or_create_queue(self, thread_id: str) -> asyncio.Queue:
        async with self._lock:
            if thread_id not in self._queues:
                self._queues[thread_id] = asyncio.Queue(maxsize=self._max_queue_size)
            return self._queues[thread_id]

    async def _cleanup_queue(self, thread_id: str):
        async with self._lock:
            self._queues.pop(thread_id, None)


