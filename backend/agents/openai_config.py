# Backend file purpose: Agent role logic for openai config processing.
from __future__ import annotations

import os
from types import ModuleType

from dotenv import load_dotenv


load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))


# Purpose: Implements the configure agent openai backend behavior.
def configure_agent_openai(openai_module: ModuleType) -> str:
    """Load OpenAI credentials/model settings for an agent module and return the configured model name."""
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if api_key and api_key not in {"your_api_key_here", "sk-dummy-key-for-testing"}:
        openai_module.api_key = api_key
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")
