"""
Render Jinja2 prompt templates from the prompts/ directory.
"""

from __future__ import annotations

import json
import os
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


def _default_prompts_dir() -> str:
    backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(backend_root, "prompts")


class PromptService:
    """Load and render agent prompts using Jinja2 FileSystemLoader."""

    def __init__(self, prompts_dir: str | None = None) -> None:
        directory = prompts_dir or _default_prompts_dir()
        if not os.path.isdir(directory):
            raise FileNotFoundError(f"Prompts directory not found: {directory}")
        self._prompts_dir = directory
        self._env = Environment(
            loader=FileSystemLoader(directory),
            autoescape=select_autoescape(enabled_extensions=()),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._env.filters["tojson"] = lambda value: json.dumps(
            value, ensure_ascii=False, indent=2, default=str
        )

    @property
    def prompts_dir(self) -> str:
        return self._prompts_dir

    def render(self, template_name: str, **variables: Any) -> str:
        """Render a template with the given variables."""
        template = self._env.get_template(template_name)
        return template.render(**variables).strip()
