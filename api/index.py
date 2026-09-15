"""Vercel Python entrypoint for the Recruitment Assist Flask API."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# The backend contains both ``app.py`` (the Flask application) and an ``app/``
# package (shared AI utilities). A normal ``from app import app`` resolves the
# package first on Vercel, so load the Flask module by its exact file path.
APP_MODULE_PATH = BACKEND / "app.py"
spec = spec_from_file_location("recruitment_assist_flask_app", APP_MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load Flask application from {APP_MODULE_PATH}")

module = module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
app = module.app
