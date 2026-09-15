# Backend file purpose: Database migration, import, or seed utility for fix admin password.
"""
Reset the seeded admin password to admin123.

Usage (from backend/):
  python database/fix_admin_password.py

Requires MONGODB_URI in .env.
"""
from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv

load_dotenv(os.path.join(BACKEND_DIR, ".env"))
import database as db  # noqa: E402


# Purpose: Coordinates the main routine for this module.
def main() -> int:
    db.init_pool()
    if db.reset_user_password("admin", "admin123"):
        print("Updated admin password to: admin123")
        return 0
    print("No row with username 'admin'. Start the app once to seed default users.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
