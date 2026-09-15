# Recruitment Assist Backend (Flask + MongoDB Atlas)

Production-oriented hiring assistant: job descriptions, resume screening, candidates, comparisons, audit trail, and dashboards. Data lives in MongoDB Atlas.

## Prerequisites

- Python 3.11+
- MongoDB Atlas cluster
- Existing `app/` package and API keys as in your current project

## 1. Environment

```bash
copy .env.example .env
```

Edit `.env` and set:

```env
MONGODB_URI=mongodb+srv://USER:PASSWORD@CLUSTER.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=recruitment_assist
SECRET_KEY=replace-with-a-long-random-secret
OPENAI_API_KEY=
```

The app creates collections and indexes automatically on startup. It also seeds these users if they do not already exist:

| Username | Password | Role |
|----------|----------|------|
| admin | admin | admin |
| recruiter | recruiter | Recruiter |
| manager | manager | Hiring Manager |

## 2. Install

From this directory:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Run

```bash
python app.py
```

Open `http://localhost:3001` when running through the root `npm run dev` script.

## Layout

| File | Role |
|------|------|
| `database.py` | MongoDB connection, numeric IDs, CRUD, metrics, audit, auth |
| `database/fix_admin_password.py` | Reset default admin password |
| `app.py` | Routes and `/api/*` bootstrap |
| `templates/`, `static/` | Legacy/static assets |

## Troubleshooting

- **`Database not configured`**: `MONGODB_URI` is missing, invalid, or Atlas network access does not allow your IP.
- **Login fails**: Start the app once so default users are seeded, or run `python database/fix_admin_password.py`.
- **LLM errors**: Configure `OPENAI_API_KEY` as required by `app/llm_extraction.py`.
