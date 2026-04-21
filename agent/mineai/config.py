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

    # llama.cpp server (OpenAI-compatible endpoint)
    llm_host:    str  = field(default_factory=lambda: os.getenv("LLM_HOST",    "localhost"))
    llm_port:    int  = field(default_factory=lambda: int(os.getenv("LLM_PORT", "8080")))
    llm_model:   str  = field(default_factory=lambda: os.getenv("LLM_MODEL",   "local-model"))
    llm_timeout: int  = field(default_factory=lambda: int(os.getenv("LLM_TIMEOUT", "60")))

    # Generation params
    max_tokens:  int  = field(default_factory=lambda: int(os.getenv("MAX_TOKENS",  "512")))
    temperature: float= field(default_factory=lambda: float(os.getenv("TEMPERATURE", "0.3")))

    # Agent behaviour
    think_interval: float = field(default_factory=lambda: float(os.getenv("THINK_INTERVAL", "3.0")))
    max_history:    int   = field(default_factory=lambda: int(os.getenv("MAX_HISTORY",      "20")))

    # Persistence
    memory_path: Path = field(default_factory=lambda: Path(os.getenv("MEMORY_PATH", "data/memory.json")))

    @property
    def llm_base_url(self) -> str:
        return f"http://{self.llm_host}:{self.llm_port}"


def load_config() -> Config:
    return Config()
