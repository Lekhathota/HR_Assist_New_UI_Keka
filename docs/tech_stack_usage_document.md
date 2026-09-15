# Recruitment Assist - Technology Stack and Usage Document

## 1. Project Overview

Recruitment Assist is a full-stack AI-powered recruitment platform. It helps recruiters manage job descriptions, upload resumes, compare candidates against jobs, schedule interviews, generate communication drafts, view dashboards, and use agentic AI workflows for screening and recruiter assistance.

At a high level, the application uses:

- React for the user interface.
- Flask for the backend API.
- MongoDB for persistent data storage.
- OpenAI for AI extraction, matching, summarization, and recruiter assistance.
- LangGraph/LangChain-style workflow orchestration for multi-step agent flows.
- Python document parsing libraries for PDF/DOCX resume and job description processing.

## 2. High-Level Architecture

```text
User Browser
   |
   | React frontend
   | RecruitmentAssist/frontend
   |
   v
Flask API backend
RecruitmentAssist/backend
   |
   | Routes, services, workflows, agents
   |
   v
MongoDB database
   |
   v
OpenAI / LangGraph / File parsing / Email / SMS integrations
```

The frontend sends requests to the backend through `frontend/src/api.js`. The backend receives those requests through Flask route modules, calls service or agent workflow logic, reads/writes MongoDB, and returns JSON responses to the React UI.

## 3. Frontend Technologies

| Technology | Where It Is Used | Why It Is Used |
|---|---|---|
| React 18 | `frontend/src/App.jsx`, `frontend/src/pages/*`, `frontend/src/components/*` | Builds the single-page application UI using reusable components and page-level views. |
| React DOM | `frontend/src/index.js` | Mounts the React application into the browser DOM. |
| React Router DOM | `frontend/src/App.jsx`, `Navbar.jsx`, page files using `Link`, `useNavigate`, `useParams` | Handles frontend navigation such as `/dashboard`, `/jobs`, `/analyze`, `/talent`, `/interviews`, `/insights`, and `/profile`. |
| Create React App / react-scripts | `frontend/package.json` | Provides development server, build process, test runner, and standard React tooling. |
| JavaScript JSX | `frontend/src/**/*.jsx` | Main language used for frontend components and page logic. |
| CSS | `frontend/src/styles/*.css`, `frontend/src/index.css` | Provides layout, branding, dashboard styling, forms, cards, candidate views, reports, and responsive UI styling. |
| Flatpickr | `frontend/src/pages/Dashboard.jsx`, `frontend/src/styles/dashboard.css` | Provides date picker controls for dashboard date filtering. |
| Fetch API | `frontend/src/api.js` | Sends HTTP requests from the frontend to Flask API endpoints. |
| Browser localStorage | `frontend/src/api.js` | Stores the user session token after login. |
| Browser sessionStorage | `frontend/src/api.js` | Caches mutable frontend data such as job description lists and clears it after changes. |
| Tailwind configuration | `frontend/tailwind.config.js` | Tailwind configuration exists for design tokens such as colors, fonts, shadows, and animations. The current UI also relies heavily on custom CSS files. |

## 4. Backend Technologies

| Technology | Where It Is Used | Why It Is Used |
|---|---|---|
| Python | `backend/**/*.py` | Main backend programming language. |
| Flask | `backend/app.py`, `backend/routes/*.py` | Provides the web server, API routes, request handling, sessions, redirects, and JSON responses. |
| Flask Blueprints | `backend/app.py`, `backend/routes/*.py` | Organizes backend routes by feature area such as auth, dashboard, jobs, candidates, matching, reports, interviews, audit, and agentic routes. |
| Flask-CORS | `backend/app.py` | Allows the React frontend on localhost ports to call Flask `/api/*` endpoints during development. |
| Werkzeug | `backend/database.py`, `backend/services/*.py` | Handles password hashing, secure file names, and Flask-related utilities. |
| python-dotenv | `backend/app.py`, `backend/agents/openai_config.py` | Loads environment variables from `.env`, such as MongoDB URI, OpenAI key, Flask settings, and communication settings. |
| Pydantic | `backend/schemas/agentic.py` | Validates structured data for agentic API requests and responses. |
| pytest | `backend/tests/test_security_hardening.py` | Provides backend automated testing. |

## 5. Database and Persistence

| Technology | Where It Is Used | Why It Is Used |
|---|---|---|
| MongoDB / MongoDB Atlas | `backend/database.py` | Stores application data such as users, job descriptions, candidates, comparisons, interviews, audit logs, agent runs, and session tokens. |
| PyMongo | `backend/database.py` | Python driver used to connect to MongoDB, create indexes, query collections, insert/update/delete documents, and manage counters. |
| MongoDB indexes | `backend/database.py` | Improves lookups and enforces uniqueness for important fields such as usernames, job IDs, candidate IDs, comparison pairs, interview IDs, and session tokens. |
| Integer ID counters | `backend/database.py` | Keeps numeric IDs for URLs and payloads while still using MongoDB documents internally. |

Main MongoDB collections used by the app:

- `users`
- `job_descriptions`
- `candidates`
- `comparisons`
- `interviews`
- `audit_logs`
- `agent_runs`
- `user_session_tokens`
- `counters`

## 6. AI and Agentic Technologies

| Technology | Where It Is Used | Why It Is Used |
|---|---|---|
| OpenAI Python SDK | `backend/app/llm_extraction.py`, `backend/agents/*.py` | Performs AI-powered extraction, resume/JD parsing, matching, ranking, summarization, interview content generation, and recruiter chat assistance. |
| LangGraph | `backend/orchestration/hr_graph.py` | Coordinates multi-step HR workflows using graph-based routing and state transitions. |
| LangChain dependency | `backend/requirements.txt` | Included as part of the AI/agent workflow stack. |
| Agent modules | `backend/agents/*.py` | Separate AI responsibilities into JD agent, resume agent, matching agent, ranking agent, summary agent, interview agent, recruiter agent, and router agent. |
| Workflow modules | `backend/workflows/*.py` | Encapsulate larger flows such as screening, recruiter chat, and application workflows. |
| Tool gateway | `backend/tools/tool_gateway.py` | Provides controlled access to backend tools and applies policy checks before agent actions. |
| Security policy | `backend/security/policy.py`, `backend/security/context_safety.py` | Adds guardrails for tool use, prompt-injection checks, and safer agent execution. |
| Agent run tracking | `backend/database.py`, `backend/routes/agentic_routes.py` | Stores agent execution metadata, task type, status, inputs, outputs, errors, and user context. |

## 7. File Upload and Document Parsing

| Technology | Where It Is Used | Why It Is Used |
|---|---|---|
| PyPDF2 | `backend/app/text_extractor.py` | Extracts text from PDF resumes and job descriptions as one fallback parser. |
| PyMuPDF | `backend/app/text_extractor.py` | Extracts PDF text using the `fitz` package, often more robust for complex PDFs. |
| pdfplumber | `backend/app/text_extractor.py` | Extracts PDF text as another fallback method, useful for layout-sensitive PDFs. |
| python-docx | `backend/app/text_extractor.py` | Extracts text from `.docx` resumes and job descriptions. |
| Werkzeug secure_filename | `backend/services/jd_service.py`, `backend/services/matching_service.py` | Sanitizes uploaded filenames before saving them. |
| Static uploads folder | `backend/static/uploads` | Stores uploaded resumes and job description files. |

The app accepts files such as `.pdf` and `.docx` for job descriptions and resumes. Text is extracted, cleaned, and then used by AI logic for structured parsing and matching.

## 8. Communication and Interview Technologies

| Technology | Where It Is Used | Why It Is Used |
|---|---|---|
| Python `smtplib` | `backend/services/interview_service.py` | Sends interview emails, follow-up emails, and cancellation emails through SMTP. |
| Python `EmailMessage` | `backend/services/interview_service.py` | Builds structured email messages before sending. |
| Twilio | `backend/services/interview_service.py`, `backend/requirements.txt` | Supports SMS/text notification workflows when Twilio credentials are configured. |
| AI-generated email content | `backend/services/interview_service.py`, `backend/agents/interview_agent.py` | Generates interview email drafts, follow-ups, and cancellation messages. |

## 9. Authentication and Security

| Technology / Pattern | Where It Is Used | Why It Is Used |
|---|---|---|
| Flask sessions | `backend/app.py`, `backend/services/auth_service.py` | Maintains authenticated backend session context. |
| Custom session token | `frontend/src/api.js`, `backend/database.py`, `backend/services/auth_service.py` | Stores a token in frontend `localStorage` and validates it against MongoDB. |
| Password hashing | `backend/database.py` | Uses Werkzeug password hashing to avoid storing plain-text passwords. |
| Protected React routes | `frontend/src/App.jsx` | Redirects unauthenticated users to `/login`. |
| Audit logs | `backend/database.py`, `backend/routes/audit_routes.py` | Records important system actions and uses hash chaining for integrity checks. |
| Prompt-injection/context safety | `backend/security/context_safety.py`, `backend/agents/recruiter_agent.py`, `backend/agents/router_agent.py` | Helps protect AI workflows from unsafe or malicious prompt content. |

## 10. API and Application Flow

### Normal frontend-to-backend flow

1. User interacts with a React page such as Dashboard, Jobs, Analyze, Candidates, or Interviews.
2. The page calls helper functions from `frontend/src/api.js`.
3. `api.js` attaches the `X-Session-Token` header.
4. Flask receives the request through a route in `backend/routes`.
5. The route calls service logic in `backend/services`.
6. Service logic reads/writes MongoDB through `backend/database.py`.
7. Flask returns JSON to the frontend.
8. React updates the UI.

### Agentic flow

1. Frontend calls `/api/agentic/run` directly or indirectly through `frontend/src/api.js`.
2. Flask handles the request in `backend/routes/agentic_routes.py`.
3. The orchestrator runs workflow logic from `backend/orchestration` and `backend/workflows`.
4. LangGraph routes the task to the correct agent or workflow.
5. Agents call OpenAI and internal tools as needed.
6. Results are persisted in MongoDB as agent runs, comparisons, candidates, or job records.
7. The final response is returned to the frontend.

## 11. Development Tooling

| Tool | Where It Is Used | Why It Is Used |
|---|---|---|
| npm | `RecruitmentAssist/package.json`, `frontend/package.json` | Runs frontend scripts and project-level development scripts. |
| concurrently | `RecruitmentAssist/package.json` | Runs Flask backend and React frontend together during development. |
| cross-env | `RecruitmentAssist/package.json` | Sets environment variables like frontend port in a cross-platform way. |
| react-scripts | `frontend/package.json` | Provides `start`, `build`, `test`, and `eject` scripts for the React app. |
| Python virtual environment | implied by backend setup scripts and Python requirements | Isolates backend dependencies. |
| requirements.txt | `backend/requirements.txt` | Lists Python backend dependencies. |
| package-lock.json | `RecruitmentAssist/package-lock.json`, `frontend/package-lock.json` | Locks Node dependency versions for reproducible installs. |

## 12. Main Feature Areas and Related Stack

| Feature | Main Files | Technologies Used |
|---|---|---|
| Login and authentication | `frontend/src/pages/Login.jsx`, `backend/routes/auth_routes.py`, `backend/services/auth_service.py`, `backend/database.py` | React, Flask, MongoDB, Werkzeug password hashing, custom session tokens |
| Dashboard | `frontend/src/pages/Dashboard.jsx`, `backend/routes/dashboard_routes.py`, `backend/services/report_service.py` | React, Flatpickr, Flask, MongoDB aggregation/count logic |
| Job descriptions | `frontend/src/pages/JdList.jsx`, `JdCreate.jsx`, `JdDetails.jsx`, `backend/routes/jd_routes.py`, `backend/services/jd_service.py` | React, Flask, file upload, PDF/DOCX parsing, OpenAI extraction, MongoDB |
| Candidate management | `frontend/src/pages/Candidates.jsx`, `CandidateProfile.jsx`, `backend/routes/candidate_routes.py`, `backend/services/candidate_service.py` | React, Flask, MongoDB, resume parsing |
| Resume/JD comparison | `frontend/src/pages/Comparison.jsx`, `backend/routes/matching_routes.py`, `backend/services/matching_service.py`, `backend/workflows/screening_workflow.py` | React multipart upload, Flask, OpenAI, agent workflow, MongoDB |
| Interviews | `frontend/src/pages/Interviews.jsx`, `backend/routes/interview_routes.py`, `backend/services/interview_service.py` | React, Flask, MongoDB, SMTP email, Twilio SMS, OpenAI email generation |
| Reports/insights | `frontend/src/pages/Reports.jsx`, `backend/routes/report_routes.py`, `backend/services/report_service.py` | React, Flask, MongoDB reporting queries |
| Recruiter chat | `frontend/src/components/FloatingRecruiterChat.jsx`, `backend/workflows/recruiter_chat_workflow.py`, `backend/agents/recruiter_agent.py` | React, Flask, OpenAI, tool gateway, MongoDB |
| Agent orchestration | `backend/orchestration/hr_graph.py`, `backend/orchestration/main_orchestrator.py`, `backend/agents/*.py` | LangGraph, OpenAI, Flask, MongoDB, policy/security modules |

## 13. Why This Stack Fits the Application

React is suitable because the application has many interactive screens, protected routes, forms, dashboards, upload flows, modals, and recruiter workflows.

Flask is suitable because the backend needs lightweight API routing, file upload handling, session handling, and easy integration with Python AI/document-processing libraries.

MongoDB is suitable because the application stores flexible recruitment data: resumes, parsed candidate profiles, job descriptions, comparisons, interviews, audit logs, and agent run outputs. These records can vary in shape, so document storage fits well.

OpenAI is suitable because the core product needs natural language understanding: extracting resume/JD details, comparing profiles, creating summaries, generating interview emails, and powering recruiter chat.

LangGraph is suitable because screening and recruiter assistance are multi-step workflows. The system needs routing, state management, agent coordination, and controlled execution rather than a single one-shot API call.

PDF/DOCX parsing libraries are required because recruiters upload real resumes and job descriptions in common document formats.

SMTP and Twilio are included because the application includes interview communication workflows through email and optional text messaging.

## 14. Summary

The application uses a modern full-stack architecture:

```text
React frontend
Flask backend
MongoDB database
OpenAI AI layer
LangGraph workflow orchestration
PDF/DOCX parsing
SMTP/Twilio communication
Custom authentication and audit logging
```

This stack supports the main goal of the application: helping recruiters move from job description and resume upload to AI-assisted candidate screening, interview scheduling, communication, reporting, and recruiter assistance.
