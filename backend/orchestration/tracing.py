# Backend file purpose: LangGraph/orchestrator infrastructure for routing backend agent tasks.
from __future__ import annotations

from datetime import datetime
import logging
import sys


_LOGGER = logging.getLogger("agentic.orchestration")
if not _LOGGER.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _LOGGER.addHandler(handler)
_LOGGER.setLevel(logging.INFO)
_LOGGER.propagate = False


# Purpose: Implements the emit backend behavior.
def _emit(line: str) -> None:
    """Write one trace line to stdout and the agentic orchestration logger."""
    print(line, flush=True)
    _LOGGER.info(line)


# Purpose: Implements the trace start backend behavior.
def trace_start(kind: str, name: str, message: str | None = None) -> None:
    """Log the start of an orchestrator, graph node, or agent step."""
    label = kind.strip().upper()
    suffix = f" - {message}" if message else ""
    _emit(f"[{label} START] {name}{suffix}")


# Purpose: Implements the trace end backend behavior.
def trace_end(kind: str, name: str, message: str | None = None) -> None:
    """Log the end of an orchestrator, graph node, or agent step."""
    label = kind.strip().upper()
    suffix = f" - {message}" if message else ""
    _emit(f"[{label} END] {name}{suffix}")


# Purpose: Implements the new run id backend behavior.
def new_run_id(prefix: str = "agentic") -> str:
    """Generate a timestamp-based run id used to track one agentic request."""
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}_{stamp}"
