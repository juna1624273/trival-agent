"""LLM Provider Factory.

Creates and configures LLM instances using the ModelPreset system.
All modern LLM providers (OpenAI, DeepSeek, Qwen, Kimi) use the OpenAI-compatible API,
so ChatOpenAI works for everything — we just vary base_url and api_key per preset.
"""

import logging
from typing import Optional
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from src.config.settings import settings

logger = logging.getLogger(__name__)


def create_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    streaming: bool = True,
    max_tokens: Optional[int] = None,
) -> BaseChatModel:
    """Create a configured LLM instance using ModelPreset auto-detection.

    Args:
        model: Model preset key (e.g. "deepseek-chat", "qwen-plus") or
               a raw model name. Defaults to settings.llm_model.
        temperature: Temperature override (defaults to settings.llm_temperature)
        streaming: Enable streaming responses
        max_tokens: Max tokens for completion
    """
    model_name = model or settings.llm_model
    preset = settings.get_model_config(model_name)
    api_key = settings.get_api_key_for_model(model_name)

    logger.debug(f"Creating LLM: model={preset.model}, base_url={preset.base_url}")

    return ChatOpenAI(
        model=preset.model,
        temperature=temperature if temperature is not None else settings.llm_temperature,
        api_key=api_key,
        base_url=preset.base_url,
        streaming=streaming,
        max_tokens=max_tokens,
    )


def create_planning_llm(model: Optional[str] = None) -> BaseChatModel:
    """Create LLM optimized for planning (low temperature for structured output)."""
    return create_llm(model=model, temperature=0.05)


def create_execution_llm(model: Optional[str] = None) -> BaseChatModel:
    """Create LLM for agent execution (moderate temperature for tool reasoning)."""
    return create_llm(model=model, temperature=0.1)


def create_summarization_llm(model: Optional[str] = None) -> BaseChatModel:
    """Create LLM for summarization (slightly higher temperature for natural language)."""
    return create_llm(model=model, temperature=0.3)
