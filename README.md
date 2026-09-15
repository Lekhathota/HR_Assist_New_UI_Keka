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
