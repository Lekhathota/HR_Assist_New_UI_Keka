"""
LangChain ChatOpenAI wrapper for agent LLM calls.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BACKEND_ROOT, ".env"))

_DEFAULT_SYSTEM = (
    "You are an expert recruiter and HR analyst. "
    "Follow the user instructions precisely. "
    "Return ONLY valid JSON when the prompt requests JSON."
)


class LLMService:
    """Execute prompts through LangChain ChatOpenAI."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> None:
        key = (api_key or os.getenv("OPENAI_API_KEY") or "").strip()
        if not key:
            raise ValueError("OPENAI_API_KEY is not configured in the environment.")
        self._model_name = (model or os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
        self._llm = ChatOpenAI(
            api_key=key,
            model=self._model_name,
            temperature=temperature,
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    def invoke(
        self,
        prompt: str,
        *,
        system_message: str = _DEFAULT_SYSTEM,
        temperature: float | None = None,
    ) -> str:
        """Send a prompt to the LLM and return response text."""
        llm: Any = self._llm
        if temperature is not None:
            llm = self._llm.bind(temperature=temperature)

        messages = [
            SystemMessage(content=system_message),
            HumanMessage(content=prompt),
        ]
        response = llm.invoke(messages)
        content = getattr(response, "content", response)
        return str(content or "").strip()
