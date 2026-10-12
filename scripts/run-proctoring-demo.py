"""Run the built app with disposable assessment data in an isolated Mongo database.

Usage: python scripts/run-proctoring-demo.py
No emails are sent and the configured recruiting database is never modified.
"""
from __future__ import annotations

import argparse
import importlib.util
from datetime import timedelta
from pathlib import Path
import random
import sys

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "backend" / ".env")
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

import database as db
from assessment import repository
from assessment.utilities import generate_access_token, utc_now


QUESTION_BANK = [
    ("What is 8 + 7?", ["15", "14", "16", "17"], "15"),
    ("Which HTTP method normally retrieves data?", ["GET", "POST", "DELETE", "PATCH"], "GET"),
    ("Which SQL clause filters rows?", ["WHERE", "ORDER BY", "GROUP BY", "SELECT"], "WHERE"),
    ("What does CSS primarily control?", ["Presentation", "Database queries", "Authentication", "Server routing"], "Presentation"),
    ("Which status code means not found?", ["404", "200", "201", "500"], "404"),
    ("Which data structure follows first in, first out?", ["Queue", "Stack", "Tree", "Set"], "Queue"),
    ("Which JavaScript method parses JSON text?", ["JSON.parse", "JSON.stringify", "Array.sort", "Object.keys"], "JSON.parse"),
    ("Which Git command shows working directory changes?", ["git status", "git init", "git clone", "git fetch"], "git status"),
    ("What is 5 squared?", ["25", "10", "15", "20"], "25"),
    ("Which HTML element is used for a button?", ["button", "section", "article", "span"], "button"),
    ("Which SQL function counts rows?", ["COUNT", "SUM", "MAX", "AVG"], "COUNT"),
    ("Which protocol encrypts normal web traffic?", ["HTTPS", "HTTP", "FTP", "Telnet"], "HTTPS"),
]


def create_demo_attempt(label: str) -> str:
    token = generate_access_token()
    now = utc_now()
    assessment_id = repository.create_assessment({
        "candidate_id": 1, "jd_id": 1, "recruiter_id": 1,
        "candidate_name": "Demo Candidate", "candidate_email": "demo@example.invalid",
        "job_role": "Practice assessment", "title": f"Proctoring test - {label}",
        "status": "SENT", "access_token": token,
        "token_expires_at": now + timedelta(days=1), "sent_at": now,
        "time_limit_minutes": 15, "passing_score": 70,
    })
    questions = []
    for text, options, answer in random.sample(QUESTION_BANK, 10):
        options = list(options)
        random.shuffle(options)
        questions.append({"question_text": text, "question_type": "mcq", "options": options,
                          "correct_answer": answer, "points": 10, "skill_tag": "Practice"})
    questions.extend([
        {"question_text": "Write a function that returns the sum of two numbers.", "question_type": "coding",
         "starter_code": "def add(a, b):\n    # Write your solution here\n", "points": 20, "skill_tag": "Python"},
        {"question_text": "Write a function that reverses a string.", "question_type": "coding",
         "starter_code": "def reverse_text(text):\n    # Write your solution here\n", "points": 20, "skill_tag": "Python"},
        {"question_text": "Select all columns from an employees table.", "question_type": "sql",
         "starter_code": "-- Write your query here\n", "points": 20, "skill_tag": "SQL"},
        {"question_text": "Count all rows in an employees table.", "question_type": "sql",
         "starter_code": "-- Write your query here\n", "points": 20, "skill_tag": "SQL"},
    ])
    repository.create_questions_bulk([
        {**question, "assessment_id": assessment_id, "sort_order": index}
        for index, question in enumerate(questions)
    ])
    return token


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5002)
    parser.add_argument("--database", default="recruitment_assist_proctoring_demo")
    args = parser.parse_args()
    if args.database == db.get_db_name() or not args.database.endswith("_proctoring_demo"):
        raise SystemExit("Use a separate database ending in _proctoring_demo; the recruiting database is protected.")
    if not (ROOT / "frontend" / "build" / "index.html").is_file():
        raise SystemExit("Build the frontend first: npm --prefix frontend run build")
    try:
        client = MongoClient(db.get_mongo_uri(), serverSelectionTimeoutMS=10000)
        client.admin.command("ping")
    except Exception as exc:
        raise SystemExit(f"Cannot connect to the configured MongoDB ({type(exc).__name__}). No demo data was created.") from None

    # Configure only this process. Bypass normal startup maintenance on recruiting data.
    db._client = client
    db._db = client[args.database]
    db._db.assessments.create_index("id", unique=True)
    db._db.assessments.create_index("access_token", unique=True, sparse=True)
    db._db.questions.create_index("id", unique=True)
    db._db.candidates.update_one({"id": 1}, {"$setOnInsert": {
        "id": 1, "name": "Demo Candidate", "email": "demo@example.invalid", "jd_id": 1,
        "status": "Selected", "match_score": 90, "structured_data": {},
    }}, upsert=True)
    db._db.job_descriptions.update_one({"id": 1}, {"$setOnInsert": {
        "id": 1, "title": "Practice assessment", "status": "Active",
    }}, upsert=True)

    # app/ is also a package, so load the Flask entrypoint explicitly.
    spec = importlib.util.spec_from_file_location("proctoring_demo_app", ROOT / "backend" / "app.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    app = module.app
    app.config["SESSION_COOKIE_SECURE"] = False
    for label in ("Primary", "Spare"):
        token = create_demo_attempt(label)
        print(f"{label}: http://localhost:{args.port}/assessment/{token}", flush=True)
    print("Isolated demo database only. Links expire in 24 hours. No emails sent.", flush=True)
    app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
