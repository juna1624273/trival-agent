"""Tests for the context compression manager."""

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from src.memory.context_manager import ContextManager


class TestContextManager:
    def test_empty_messages(self):
        cm = ContextManager(max_tokens=1000)
        result = cm.compress([])
        assert result == []

    def test_preserves_all_when_under_limit(self):
        cm = ContextManager(max_tokens=100000)
        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there"),
        ]
        result = cm.compress(messages)
        assert len(result) == 3

    def test_preserves_tool_messages(self):
        cm = ContextManager(max_tokens=50, keep_recent=1)
        messages = [
            HumanMessage(content="Hello " * 200),  # long message
            ToolMessage(content="Important tool result", tool_call_id="t1"),
        ]
        result = cm.compress(messages)
        # Tool message should be preserved
        tool_msgs = [m for m in result if isinstance(m, ToolMessage)]
        assert len(tool_msgs) == 1
        assert tool_msgs[0].content == "Important tool result"

    def test_preserves_system_messages(self):
        cm = ContextManager(max_tokens=50, keep_recent=1)
        messages = [
            SystemMessage(content="Important system prompt"),
            HumanMessage(content="Long message " * 100),
        ]
        result = cm.compress(messages)
        sys_msgs = [m for m in result if isinstance(m, SystemMessage)]
        assert len(sys_msgs) == 1

    def test_truncates_long_human_messages(self):
        cm = ContextManager(max_tokens=100, keep_recent=1)
        long_text = "A" * 500
        messages = [
            HumanMessage(content=long_text),
            AIMessage(content="Short reply"),
        ]
        result = cm.compress(messages)
        # Should have 2 messages (compressed human + recent AIMessage)
        assert len(result) == 2
        # First message should be truncated
        human_msg = result[0]
        assert isinstance(human_msg, HumanMessage)
        assert len(human_msg.content) < len(long_text)

    def test_handles_empty_content(self):
        cm = ContextManager(max_tokens=100)
        messages = [
            HumanMessage(content=""),
            AIMessage(content=""),
        ]
        result = cm.compress(messages)
        assert len(result) == 2

    def test_token_estimation(self):
        cm = ContextManager()
        messages = [
            HumanMessage(content="Hello World"),  # ~2.75 tokens
        ]
        estimated = cm._estimate_tokens(messages)
        assert estimated > 0
        assert estimated < 20  # should be very small
