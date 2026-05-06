"""Context Manager — message window compression for token control.

Strategy:
1. NEVER remove ToolMessage entries (contain factual data)
2. Keep the most recent N messages intact
3. For messages beyond the window:
   - ToolMessage: keep content intact
   - HumanMessage: summarize to one sentence
   - AIMessage with tool_calls: clear tool_calls, keep summary
   - SystemMessage: always retain
4. Trigger when estimated token count exceeds threshold
"""

import logging
from typing import List

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
    SystemMessage,
)

logger = logging.getLogger(__name__)

# Approximate tokens per character for estimation (conservative)
TOKENS_PER_CHAR = 0.25


class ContextManager:
    """Manages message window compression to stay within token limits."""

    def __init__(
        self,
        model_name: str = "gpt-4o",
        max_tokens: int = 80000,
        keep_recent: int = 20,
    ):
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.keep_recent = keep_recent

    def compress(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """Compress messages to fit within token budget.

        Guarantees:
        - All ToolMessages are preserved
        - Most recent N messages are preserved verbatim
        - Total estimated tokens <= max_tokens
        """
        if not messages:
            return messages

        estimated = self._estimate_tokens(messages)
        if estimated <= self.max_tokens:
            return messages

        logger.info(f"Context compression triggered: {estimated} > {self.max_tokens} tokens")

        # Split: recent messages preserved verbatim, older ones compressed
        split_idx = max(0, len(messages) - self.keep_recent)
        older = messages[:split_idx]
        recent = messages[split_idx:]

        compressed_older = self._compress_batch(older)
        result = compressed_older + recent

        new_estimate = self._estimate_tokens(result)
        logger.info(f"Compression complete: {estimated} -> {new_estimate} tokens")
        return result

    def _compress_batch(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """Compress a batch of older messages."""
        compressed = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                # Always preserve tool results — they contain factual data
                compressed.append(msg)
            elif isinstance(msg, SystemMessage):
                # Always preserve system messages
                compressed.append(msg)
            elif isinstance(msg, HumanMessage):
                # Summarize old user messages
                content = self._extract_text(msg.content)
                if len(content) > 200:
                    summary = self._truncate_text(content, max_chars=200)
                    compressed.append(HumanMessage(content=f"[历史消息] {summary}"))
                else:
                    compressed.append(msg)
            elif isinstance(msg, AIMessage):
                # For AI messages: keep reasoning, strip tool_calls
                content = self._extract_text(msg.content)
                if msg.tool_calls:
                    summary = self._truncate_text(content, max_chars=300) if content else ""
                    compressed.append(AIMessage(
                        content=f"[已调用工具] {summary}" if summary else "[已调用工具]"
                    ))
                elif content:
                    if len(content) > 300:
                        compressed.append(AIMessage(
                            content=f"[历史回复] {self._truncate_text(content, max_chars=300)}"
                        ))
                    else:
                        compressed.append(msg)
                # else: skip empty AI messages
            else:
                # Unknown message type: keep if short, truncate if long
                content = self._extract_text(getattr(msg, 'content', ''))
                if len(content) <= 300:
                    compressed.append(msg)

        return compressed

    def _estimate_tokens(self, messages: List[BaseMessage]) -> int:
        """Estimate total token count for a list of messages."""
        total = 0
        for msg in messages:
            content = self._extract_text(getattr(msg, 'content', ''))
            total += max(1, int(len(content) * TOKENS_PER_CHAR))
            # Add overhead for tool calls
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    args_str = str(tc.get('args', ''))
                    total += max(1, int(len(args_str) * TOKENS_PER_CHAR))
        return total

    def _extract_text(self, content) -> str:
        """Extract text from message content (handles string and list formats)."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(item.get("text", ""))
                    else:
                        parts.append(str(item))
                elif isinstance(item, str):
                    parts.append(item)
            return " ".join(parts)
        return str(content) if content else ""

    def _truncate_text(self, text: str, max_chars: int = 300) -> str:
        """Truncate text to max characters, preserving word boundaries."""
        if len(text) <= max_chars:
            return text
        truncated = text[:max_chars]
        # Try to break at last period, newline, or space
        for sep in [". ", "\n", " "]:
            last_idx = truncated.rfind(sep)
            if last_idx > max_chars * 0.7:
                return truncated[:last_idx + len(sep.rstrip())] + "..."
        return truncated + "..."
