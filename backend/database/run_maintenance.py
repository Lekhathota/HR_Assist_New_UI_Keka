"""Run database indexes, seeds and backfills once, outside request cold starts."""
from pathlib import Path
import os
import sys
from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
load_dotenv(BACKEND / '.env')
load_dotenv(BACKEND.parent / '.env')
os.environ['RA_RUN_DB_MAINTENANCE'] = 'true'

if __name__ == '__main__':
    import database as db
    try:
        db.init_pool()
        print('Database maintenance completed.')
    finally:
        db.close_pool()
