"""Run SQL answers against throwaway in-memory SQLite databases.

Each test case builds a fresh database from the question schema plus the
case's dataset, then runs one read-only query. Candidate SQL can only read:
an authorizer denies writes, schema changes, ATTACH, PRAGMA and extension
loading, and a progress handler aborts runaway queries.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Optional

MAX_ROWS = 1000
DEFAULT_TIMEOUT_SECONDS = 3.0

_READ_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}
_BLOCKED_FUNCTIONS = {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"}


class SqlExecutionError(Exception):
    """The query could not run (syntax error, forbidden statement, timeout)."""


@dataclass
class SqlResult:
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    truncated: bool = False


def _read_only_authorizer(action, arg1, arg2, db_name, trigger):
    if action == sqlite3.SQLITE_FUNCTION and str(arg2 or "").lower() in _BLOCKED_FUNCTIONS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK if action in _READ_ACTIONS else sqlite3.SQLITE_DENY


def _setup_authorizer(action, arg1, arg2, db_name, trigger):
    # Schema/dataset scripts come from the question author, but still may not escape the sandbox.
    if action in {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA}:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and str(arg2 or "").lower() in _BLOCKED_FUNCTIONS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _clean_query(query: str) -> str:
    text = str(query or "").strip()
    while text.endswith(";"):
        text = text[:-1].rstrip()
    if not text:
        raise SqlExecutionError("The query is empty.")
    return text


def run_query(schema_sql: str, dataset_sql: str, query: str, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> SqlResult:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    deadline = time.monotonic() + timeout_seconds
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    try:
        conn.set_authorizer(_setup_authorizer)
        try:
            conn.executescript(f"{schema_sql or ''}\n{dataset_sql or ''}")
        except sqlite3.Error as exc:
            raise SqlExecutionError(f"Test data could not be loaded: {exc}") from exc
        conn.set_authorizer(_read_only_authorizer)
        try:
            cursor = conn.execute(_clean_query(query))
            columns = [d[0] for d in cursor.description or []]
            rows = cursor.fetchmany(MAX_ROWS + 1)
        except sqlite3.Warning as exc:
            raise SqlExecutionError("Submit a single SELECT query (multiple statements are not allowed).") from exc
        except sqlite3.OperationalError as exc:
            message = str(exc)
            if "interrupted" in message:
                raise SqlExecutionError(f"The query took longer than {timeout_seconds:g} seconds.") from exc
            if "not authorized" in message:
                raise SqlExecutionError("Only read-only SELECT queries are allowed.") from exc
            raise SqlExecutionError(message) from exc
        except sqlite3.Error as exc:
            message = str(exc)
            if "not authorized" in message:
                raise SqlExecutionError("Only read-only SELECT queries are allowed.") from exc
            if "one statement at a time" in message:
                raise SqlExecutionError("Submit a single SELECT query (multiple statements are not allowed).") from exc
            raise SqlExecutionError(message) from exc
        if not columns:
            raise SqlExecutionError("The statement returned no result set; submit a SELECT query.")
        return SqlResult(columns=columns, rows=[list(r) for r in rows[:MAX_ROWS]], truncated=len(rows) > MAX_ROWS)
    finally:
        conn.close()


def _norm_value(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, float):
        rounded = round(value, 6)
        return int(rounded) if rounded.is_integer() else rounded
    if isinstance(value, bytes):
        return value.hex()
    return value


def normalize_rows(rows: list[list[Any]], order_matters: bool) -> list[tuple]:
    normalized = [tuple(_norm_value(v) for v in row) for row in rows]
    if order_matters:
        return normalized
    return sorted(normalized, key=lambda row: tuple((v is None, str(type(v).__name__), str(v)) for v in row))


def results_match(actual: SqlResult, expected: dict, order_matters: bool) -> bool:
    expected_rows = expected.get("rows") or []
    if expected_rows and actual.rows and len(actual.rows[0]) != len(expected_rows[0]):
        return False
    if not expected_rows and actual.columns and expected.get("columns") and len(actual.columns) != len(expected["columns"]):
        return False
    return normalize_rows(actual.rows, order_matters) == normalize_rows(expected_rows, order_matters)


def expected_from_reference(schema_sql: str, dataset_sql: str, reference_query: str) -> dict:
    result = run_query(schema_sql, dataset_sql, reference_query)
    return {"columns": result.columns, "rows": [[_norm_value(v) for v in row] for row in result.rows]}


def preview_rows(result: Optional[SqlResult], limit: int = 20) -> dict:
    if result is None:
        return {"columns": [], "rows": []}
    return {"columns": result.columns, "rows": [[_norm_value(v) for v in row] for row in result.rows[:limit]],
            "row_count": len(result.rows)}
