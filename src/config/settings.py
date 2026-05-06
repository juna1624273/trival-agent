from pydantic_settings import BaseSettings
from typing import Optional, Dict, List
from dataclasses import dataclass


@dataclass
class ModelPreset:
    """Preset configuration for a supported model provider."""
    model: str
    base_url: str
    api_key_env: str  # name of the env var holding the API key
    label: str        # display name in frontend


# Preset model configurations — add new ones here
MODEL_PRESETS: Dict[str, ModelPreset] = {
    # ── DeepSeek ──
    "deepseek-v4-flash": ModelPreset(
        model="deepseek-v4-flash", base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY", label="DeepSeek V4 Flash",
    ),
    "deepseek-v4-pro": ModelPreset(
        model="deepseek-v4-pro", base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY", label="DeepSeek V4 Pro",
    ),
    # 以下旧名称保留兼容，日后将弃用
    "deepseek-chat": ModelPreset(
        model="deepseek-chat", base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY", label="DeepSeek V3 (旧)",
    ),
    "deepseek-reasoner": ModelPreset(
        model="deepseek-reasoner", base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY", label="DeepSeek R1 (旧)",
    ),

    # ── 通义千问 (Qwen) ──
    "qwen-plus": ModelPreset(
        model="qwen-plus", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="QWEN_API_KEY", label="通义千问 Plus",
    ),
    "qwen-max": ModelPreset(
        model="qwen-max", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="QWEN_API_KEY", label="通义千问 Max",
    ),
    "qwen-turbo": ModelPreset(
        model="qwen-turbo", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="QWEN_API_KEY", label="通义千问 Turbo",
    ),

    # ── Kimi (Moonshot) ──
    "moonshot-v1-8k": ModelPreset(
        model="moonshot-v1-8k", base_url="https://api.moonshot.cn/v1",
        api_key_env="KIMI_API_KEY", label="Kimi 8K",
    ),
    "moonshot-v1-32k": ModelPreset(
        model="moonshot-v1-32k", base_url="https://api.moonshot.cn/v1",
        api_key_env="KIMI_API_KEY", label="Kimi 32K",
    ),
    "moonshot-v1-128k": ModelPreset(
        model="moonshot-v1-128k", base_url="https://api.moonshot.cn/v1",
        api_key_env="KIMI_API_KEY", label="Kimi 128K",
    ),

    # ── OpenAI / 兼容 ──
    "gpt-4o": ModelPreset(
        model="gpt-4o", base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY", label="GPT-4o",
    ),
    "gpt-4o-mini": ModelPreset(
        model="gpt-4o-mini", base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY", label="GPT-4o Mini",
    ),
}

# Flattened list for frontend (id → label)
def get_available_models() -> List[Dict[str, str]]:
    return [{"id": k, "label": v.label} for k, v in MODEL_PRESETS.items()]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── LLM ──
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.1

    # Provider-specific API keys
    deepseek_api_key: str = ""
    qwen_api_key: str = ""
    kimi_api_key: str = ""

    # ── MCP Server URLs ──
    amap_mcp_url: str = "http://127.0.0.1:8100/mcp"
    amap_api_key: str = ""
    railway_mcp_url: str = "http://127.0.0.1:8101/mcp"
    flight_mcp_url: str = "http://127.0.0.1:8102/mcp"
    weather_mcp_url: str = "http://127.0.0.1:8103/mcp"
    weather_api_key: str = ""
    hotel_mcp_url: str = "http://127.0.0.1:8104/mcp"
    search_mcp_url: str = "http://127.0.0.1:8105/mcp"
    search_api_key: str = ""

    # ── Redis ──
    redis_url: str = "redis://127.0.0.1:6379/0"

    # ── ChromaDB ──
    chroma_persist_dir: str = "./data/chroma"

    # ── Context Management ──
    max_context_tokens: int = 80000
    keep_recent_messages: int = 20

    # ── Cache TTL (minutes) ──
    cache_ttl_weather: int = 60
    cache_ttl_hotel: int = 240
    cache_ttl_transport: int = 120
    cache_ttl_search: int = 1440
    cache_similarity_threshold: float = 0.92

    # ── ReAct ──
    max_react_iterations: int = 3
    max_parallel_steps: int = 5  # max steps to execute concurrently in one batch

    # ── Server ──
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def get_model_config(self, model_name: Optional[str] = None) -> ModelPreset:
        """Resolve a model name to its preset config. Falls back to default if unknown."""
        name = model_name or self.llm_model
        if name in MODEL_PRESETS:
            return MODEL_PRESETS[name]
        # Unknown model — treat as OpenAI-compatible using the generic settings
        return ModelPreset(
            model=name, base_url=self.openai_base_url,
            api_key_env="OPENAI_API_KEY", label=name,
        )

    def get_api_key_for_model(self, model_name: Optional[str] = None) -> str:
        """Get the API key for a model by checking its preset's env var."""
        preset = self.get_model_config(model_name)
        env_key = preset.api_key_env
        # Map env var name to the actual value
        key_map = {
            "OPENAI_API_KEY": self.openai_api_key,
            "DEEPSEEK_API_KEY": self.deepseek_api_key,
            "QWEN_API_KEY": self.qwen_api_key,
            "KIMI_API_KEY": self.kimi_api_key,
        }
        return key_map.get(env_key, self.openai_api_key)


settings = Settings()
