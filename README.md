# ShimentoX Talent Intelligence Platform

Cleaned project structure with a single React frontend and a single Flask backend.

## Structure

```text
RecruitmentAssist/
├── backend/
│   ├── agents/
│   ├── app/
│   ├── assessment/
│   ├── database/
│   ├── orchestration/
│   ├── prompts/
│   ├── routes/
│   ├── schemas/
│   ├── security/
│   ├── services/
│   ├── tools/
│   ├── app.py
│   ├── database.py
│   └── requirements.txt
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── styles/
│   │   ├── utils/
│   │   ├── App.jsx
│   │   └── index.js
│   ├── package.json
│   └── package-lock.json
├── api/
├── docs/
├── scripts/
├── app.yaml
├── package.json
└── vercel.json
```

## UI theme

The old blue/classic theme has been removed from the active application. The current ShimentoX black/white/graphite UI with orange accent is the single canonical theme.

## Development

From the project root:

```bash
npm install
npm run dev
```

The helper scripts start the Flask backend and React development server together.

Or run them separately:

```bash
cd backend
python app.py
```

and:

```bash
cd frontend
npm install
npm start
```

Keep secrets in `backend/.env`. Do not commit `.env`.

## Vercel deployment

Configure the existing MongoDB connection and application secrets in Vercel environment variables, then redeploy. Local `.env` files are excluded from the function bundle.

On Vercel, uploaded resumes and JDs are persisted in MongoDB GridFS (`uploaded_documents`) while extraction uses temporary files that are removed after each request. Authenticated original-file access uses `/api/uploads/<filename>`. Local development continues to store files in `backend/static/uploads`.

Vercel requests have a 4.5 MB payload limit; keep each upload batch below 4 MB including all files. Larger uploads require a separate direct-upload storage flow.

Database migrations, index creation, and maintenance no longer run during every serverless cold start. Run `python backend/database/run_maintenance.py` once against the deployment database when setting up or upgrading it, using the same MongoDB configuration. Do not permanently enable `RA_RUN_DB_MAINTENANCE` in Vercel; it restores startup maintenance only when explicitly set to `true`.

## JD-based assessments

Hiring Pipeline assessments generate 14 JD-based scenario questions in every assessment: 10 MCQs (4 moderate and 6 hard), 2 moderate coding questions, and 2 moderate SQL questions. Complexity is calibrated to JD experience. Coding uses a JD language/tool or pseudocode; SQL tasks use data relevant to JD responsibilities. Drafts can be replaced using **Regenerate from JD**. Candidate information is used only to assign and deliver an assessment.

Assessment generation and review default to `gpt-4.1`, with an independent JD relevance and question-quality review. Set `ASSESSMENT_MODEL` in `backend/.env` to override this model. Generation requires the existing `OPENAI_API_KEY`. Invalid exams are retried up to three times; failure preserves the existing draft and never inserts generic fallback questions.

The authenticated `POST /api/assessment/exam/generate` endpoint accepts `{ "jd_id": 27 }` and returns the requested exam JSON without requiring a candidate or saving an assignment. Answer explanations and evaluation details appear only in recruiter responses.
