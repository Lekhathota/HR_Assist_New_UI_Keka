# Backend file purpose: Database migration, import, or seed utility for migrate json to db.
"""
Migrate legacy JSON files under ./data/ into PostgreSQL.

From backend/:
  python database/migrate_json_to_db.py --apply-schema   # create tables, then migrate
  python database/migrate_json_to_db.py                  # migrate only (tables must already exist)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Json
from werkzeug.security import generate_password_hash

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env")
DATA = BACKEND_DIR / "data"
SCHEMA_FILE = SCRIPT_DIR / "schema.sql"
PROCEDURES_FILE = SCRIPT_DIR / "procedures.sql"


# Purpose: Implements the apply sql file backend behavior.
def apply_sql_file(dsn: str, path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {path}")
    body = path.read_text(encoding="utf-8")
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(body)


# Purpose: Implements the apply schema sql backend behavior.
def apply_schema_sql(dsn: str) -> None:
    apply_sql_file(dsn, SCHEMA_FILE)
    if PROCEDURES_FILE.is_file():
        apply_sql_file(dsn, PROCEDURES_FILE)


# Purpose: Implements the users table exists backend behavior.
def users_table_exists(dsn: str) -> bool:
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'users'
                )
                """
            )
            row = cur.fetchone()
    return bool(row and row[0])


# Purpose: Loads json for later processing.
def load_json(name: str):
    path = DATA / name
    if not path.exists():
        return [] if name != "users.json" else []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# Purpose: Coordinates the main routine for this module.
def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Recruitment Assist JSON data to PostgreSQL.")
    parser.add_argument(
        "--apply-schema",
        action="store_true",
        help="Create tables before first migration.",
    )
    args = parser.parse_args()

    dsn = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_DSN")
    if not dsn:
        print("Set DATABASE_URL or POSTGRES_DSN in .env or the environment.", file=sys.stderr)
        return 1

    if args.apply_schema:
        if users_table_exists(dsn):
            print("Note: table 'users' already exists — skipping schema apply.", file=sys.stderr)
        else:
            print("Applying schema from database/schema.sql …")
            try:
                apply_schema_sql(dsn)
            except Exception as e:
                print(f"Failed to apply schema: {e}", file=sys.stderr)
                return 1
            print("Schema applied.")

    if not users_table_exists(dsn):
        print(
            "\nERROR: The database has no tables yet (relation \"users\" does not exist).\n\n"
            "Do one of the following:\n"
            "  • Run:  python database/migrate_json_to_db.py --apply-schema\n"
            "  • Or open database/schema.sql in pgAdmin / DBeaver and execute it against your database.\n"
            "  • Or from a shell:  psql \"YOUR_DATABASE_URL\" -f database/schema.sql\n\n"
            "Then run this script again without --apply-schema (or with it if the DB is still empty).\n",
            file=sys.stderr,
        )
        return 1

    import database as db

    db.init_pool()

    users = load_json("users.json")
    if not isinstance(users, list):
        users = []

    jds = load_json("jds.json")
    if not isinstance(jds, list):
        jds = []

    candidates = load_json("candidates.json")
    if not isinstance(candidates, list):
        candidates = []

    comparisons = load_json("comparisons.json")
    if not isinstance(comparisons, list):
        comparisons = []

    audit_logs = load_json("audit_logs.json")
    if not isinstance(audit_logs, list):
        audit_logs = []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for u in users:
                uname = u.get("username") or ""
                if uname.lower() == "admin":
                    continue
                pwd = u.get("password", "") or ""
                if pwd and not (pwd.startswith("pbkdf2:") or pwd.startswith("scrypt:")):
                    pwd = generate_password_hash(pwd)
                role = u.get("role") or "user"
                if isinstance(role, str):
                    role = role.strip()[:50]
                cur.execute(
                    """
                    CALL migrate_upsert_user(
                        %s::varchar,
                        %s::varchar,
                        %s::varchar,
                        %s::varchar
                    )
                    """,
                    (uname, pwd, u.get("email") or "", role),
                )

            for jd in jds:
                created = jd.get("created") or datetime.now().isoformat()
                skills = jd.get("skills") or []
                resp = jd.get("responsibilities")
                if resp is None and isinstance(jd.get("structured_data"), dict):
                    resp = jd["structured_data"].get("responsibilities") or []
                cur.execute(
                    """
                    CALL migrate_upsert_jd(
                        %s::integer,
                        %s::varchar,
                        %s::varchar,
                        %s::varchar,
                        %s::text,
                        %s::text[],
                        %s::text[],
                        %s::jsonb,
                        %s::text,
                        %s::varchar,
                        %s::varchar,
                        %s::timestamptz,
                        %s::timestamptz
                    )
                    """,
                    (
                        jd["id"],
                        jd.get("title") or "",
                        jd.get("department") or "",
                        jd.get("location") or "",
                        jd.get("experience") or jd.get("experience_required") or "",
                        skills,
                        list(resp) if resp else [],
                        Json(jd.get("structured_data") or {}),
                        jd.get("raw_text") or "",
                        jd.get("file") or jd.get("file_name") or "",
                        jd.get("status") or "Active",
                        created,
                        created,
                    ),
                )

            for c in candidates:
                sd = c.get("structured_data") or {}
                phone = c.get("phone") or ""
                if isinstance(sd, dict) and not phone:
                    phone = sd.get("phone") or ""
                uploaded = c.get("uploaded") or datetime.now().isoformat()
                cur.execute(
                    """
                    CALL migrate_upsert_candidate(
                        %s::integer,
                        %s::varchar,
                        %s::varchar,
                        %s::varchar,
                        %s::text[],
                        %s::jsonb,
                        %s::integer,
                        %s::varchar,
                        %s::text,
                        %s::text,
                        %s::varchar,
                        %s::varchar,
                        %s::timestamptz,
                        %s::integer
                    )
                    """,
                    (
                        c["id"],
                        c.get("name") or "",
                        c.get("email") or "",
                        phone or "",
                        c.get("applied_roles") or [],
                        Json(sd if isinstance(sd, dict) else {}),
                        int(c.get("match_score") or 0),
                        c.get("status") or "Pending",
                        c.get("screening_summary") or "",
                        c.get("rejection_reason") or "",
                        c.get("hiring_stage") or "",
                        c.get("resume_file") or "",
                        uploaded,
                        c.get("jd_id"),
                    ),
                )

            for co in comparisons:
                cur.execute(
                    """
                    CALL migrate_upsert_comparison(
                        %s::integer,
                        %s::integer,
                        %s::integer,
                        %s::integer,
                        %s::varchar,
                        %s::text[],
                        %s::text[],
                        %s::text,
                        %s::text,
                        %s::timestamptz
                    )
                    """,
                    (
                        co["id"],
                        co["jd_id"],
                        co["candidate_id"],
                        int(co.get("match_score") or 0),
                        co.get("status") or "Pending",
                        co.get("strengths") or [],
                        co.get("gaps") or [],
                        co.get("recommendation") or "",
                        co.get("failure_reason") or "",
                        co.get("comparison_date") or datetime.now().isoformat(),
                    ),
                )

            for a in audit_logs:
                raw_jd = a.get("jd_id")
                if raw_jd is None or (isinstance(raw_jd, (int, float)) and int(raw_jd) <= 0):
                    audit_jd_id = None
                else:
                    audit_jd_id = int(raw_jd)
                cur.execute(
                    """
                    CALL migrate_insert_audit_log(
                        %s::text,
                        %s::text,
                        %s::text,
                        %s::integer,
                        %s::timestamptz
                    )
                    """,
                    (
                        a.get("action") or "",
                        a.get("username") or a.get("user") or "",
                        a.get("details") or "",
                        audit_jd_id,
                        a.get("timestamp") or datetime.now().isoformat(),
                    ),
                )

            cur.execute("CALL resync_id_sequences()")

        conn.commit()

    print("Migration completed successfully.")
    db.close_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
