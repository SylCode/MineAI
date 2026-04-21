"""
config.py – loads agent configuration from environment variables or a .env
file at the project root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Optional: load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass


@dataclass
class Config:
    # Bot WebSocket
    bot_host:    str  = field(default_factory=lambda: os.getenv("BOT_HOST",    "localhost"))
    bot_ws_port: int  = field(default_factory=lambda: int(os.getenv("BOT_WS_PORT", "3001")))

    # Fast/local LLM – used for every ReAct think cycle (llama.cpp or similar)
    llm_host:    str  = field(default_factory=lambda: os.getenv("LLM_HOST",    "localhost"))
    llm_port:    int  = field(default_factory=lambda: int(os.getenv("LLM_PORT", "8080")))
    llm_model:   str  = field(default_factory=lambda: os.getenv("LLM_MODEL",   "local-model"))
    llm_timeout: int  = field(default_factory=lambda: int(os.getenv("LLM_TIMEOUT", "60")))
    llm_api_key: str | None = field(default_factory=lambda: os.getenv("LLM_API_KEY") or None)

    # Strong/cloud LLM – used for curriculum, critic, and skill generation
    # Leave STRONG_LLM_BASE_URL empty to use the same local LLM for everything.
    strong_llm_base_url: str       = field(default_factory=lambda: os.getenv("STRONG_LLM_BASE_URL", ""))
    strong_llm_model:    str       = field(default_factory=lambda: os.getenv("STRONG_LLM_MODEL",    "gpt-4.1"))
    strong_llm_api_key:  str | None= field(default_factory=lambda: os.getenv("STRONG_LLM_API_KEY") or None)
    strong_llm_timeout:  int       = field(default_factory=lambda: int(os.getenv("STRONG_LLM_TIMEOUT", "120")))

    # Generation params
    max_tokens:  int  = field(default_factory=lambda: int(os.getenv("MAX_TOKENS",  "512")))
    temperature: float= field(default_factory=lambda: float(os.getenv("TEMPERATURE", "0.3")))

    # Agent behaviour
    think_interval: float = field(default_factory=lambda: float(os.getenv("THINK_INTERVAL", "3.0")))
    max_history:    int   = field(default_factory=lambda: int(os.getenv("MAX_HISTORY",      "20")))

    # Voyager-style improvements
    max_retries:          int = field(default_factory=lambda: int(os.getenv("MAX_RETRIES",          "2")))
    curriculum_interval:  int = field(default_factory=lambda: int(os.getenv("CURRICULUM_INTERVAL",  "10")))
    skill_top_k:          int = field(default_factory=lambda: int(os.getenv("SKILL_TOP_K",          "3")))
    skill_fail_threshold: int = field(default_factory=lambda: int(os.getenv("SKILL_FAIL_THRESHOLD", "3")))

    # Persistence
    memory_path:      Path = field(default_factory=lambda: Path(os.getenv("MEMORY_PATH",      "data/memory.json")))
    skill_chroma_path:Path = field(default_factory=lambda: Path(os.getenv("SKILL_CHROMA_PATH","data/skill_chroma")))

    @property
    def llm_base_url(self) -> str:
        return f"http://{self.llm_host}:{self.llm_port}"

    @property
    def strong_llm_effective_url(self) -> str:
        """Returns the strong LLM base URL, or the local LLM URL as fallback."""
        return self.strong_llm_base_url.rstrip("/") or self.llm_base_url

    @property
    def strong_llm_effective_model(self) -> str:
        return self.strong_llm_model if self.strong_llm_base_url else self.llm_model

    @property
    def strong_llm_effective_key(self) -> str | None:
        return self.strong_llm_api_key if self.strong_llm_base_url else self.llm_api_key


def load_config() -> Config:
    return Config()
