# Automated Interview Rescheduling & No-Show Recovery

Reschedule requests and no-shows are handled without the recruiter. The recruiter is pulled in only when automation cannot finish (attempts exhausted, no mutual slot, unrecoverable delivery/integration failure).

Code: `backend/interview_recovery/` (config, models, repository, providers, slots, service), routes in `backend/routes/interview_recovery_routes.py`, candidate page `frontend/src/pages/InterviewResponse.jsx` (`/interview/:token`), recruiter UI in `frontend/src/pages/Interviews.jsx` (Hiring Pipeline → Interviews).

## How candidates reach it

Each interview gets a private **manage link** `<CANDIDATE_TEST_BASE_URL>/interview/<token>` (same token model as assessment links).

- New interviews: the link is appended to the invitation email when `CANDIDATE_TEST_BASE_URL` is set to a public URL.
- Existing interviews: a token is created the first time automation emails the candidate.
- Candidates who email or phone the recruiter instead: the recruiter clicks **Candidate asked to reschedule** on the interview card; automation takes over from there.

## Workflow

```
Reschedule request ─► PENDING ─► slot search ─► SLOT_PROPOSED ─► candidate picks ─► re-check ─► RESCHEDULED
No-show            ─► PENDING ─► outreach    ─► AWAITING_RESPONSE ─► "yes" ─► SLOT_PROPOSED ─► ... ─► RECOVERED
                                                                   └► "no"  ─► CLOSED (recruiter informed)
No slots / no reply / delivery failure ─► RETRY_SCHEDULED ─► ... ─► ESCALATED (recruiter notified once)
```

1. **Reschedule request** (candidate page or recruiter-logged) creates a case and runs the slot search *in the same request*, so options go out within seconds. No recruiter action.
2. **Slot search** uses the recruiter's booked interviews (and the candidate's other interviews), interview duration, working hours/days, minimum notice and any availability windows the candidate entered. It offers up to `SLOT_COUNT` slots spread across different days and never re-offers the current time or slots found to be taken.
3. **Confirmation** re-checks availability under a per-recruiter booking lock before updating the *existing* interview record (no duplicate interview). If the slot was taken meanwhile it is not booked; fresh options are shown instead.
4. **After booking**: candidate gets a confirmation email; the recruiter gets an in-app notification (informational, no action needed) and is asked to tell the interviewer, because interviewers are free-text names without contact details.
5. **No-show**: after `INTERVIEW_NO_SHOW_GRACE_MINUTES`, the interview is marked `No Show` and the candidate is emailed asking whether they want a new time (Yes → slot proposal flow, No → case closed, recruiter informed).
6. **Stops automatically** when the interview is cancelled, completed (Selected/Rejected), rescheduled by the recruiter, marked attended, or deleted.

### No-show detection modes (`INTERVIEW_NO_SHOW_DETECTION`)

HR Assist has no attendance feed from a meeting provider, so "the candidate did not attend" needs a signal:

- `confirmed` (default): the recruiter/interviewer clicks **No-show** on a past interview. Recovery then runs automatically. This avoids messaging candidates who attended an interview nobody marked.
- `auto`: every scheduler run treats active interviews with no attendance recorded, past the grace period and within `INTERVIEW_NO_SHOW_LOOKBACK_HOURS`, as no-shows. Use only if interviewers reliably click **Attended**.

### Attempts, retries and escalation

| Situation | Counts as attempt? | What happens |
|---|---|---|
| Options / no-show message delivered | yes | wait `RESPONSE_TIMEOUT_MINUTES` |
| No reply by the deadline | (the delivered message already counted) | resend fresh options / reminder, or escalate when `attempt_count >= MAX_ATTEMPTS` |
| Slot search finds nothing | yes | retry after `RETRY_DELAY_MINUTES`, escalate at the limit |
| Transient delivery failure (SMTP timeout etc.) | no (`delivery_failure_count`) | exponential backoff from `RETRY_DELAY_MINUTES` (max 24 h), escalate after `MAX_DELIVERY_FAILURES` |
| Permanent delivery failure (no email, SMTP not configured, link URL missing) | no | escalate immediately |
| Unexpected worker error | no (`error_count`) | retry later, escalate after `MAX_DELIVERY_FAILURES` |
| Slot taken during confirmation | no | new options offered immediately |

Escalation is idempotent (`escalated_at` is set atomically once): one in-app notification plus one email to the interview's recruiter, containing the interview/candidate reference, reason, recommended next step and attempt history. **Retry** on an escalated case resets the counters and allows a fresh escalation later; **Close case** ends it.

### Reliability

- One open case per interview and type (partial unique index); duplicate clicks or detection runs reuse it.
- No-show cases are tied to the specific interview time, so re-running detection never re-contacts the candidate.
- Every scheduler action starts with an atomic claim that sets a lease (`INTERVIEW_RECOVERY_LEASE_SECONDS`). If a serverless invocation dies, the case is picked up after the lease expires. A booking interrupted after the interview was updated is completed, not re-booked.
- Every message, delivery result, provider message id (SMS), search, timeout, booking and escalation is stored in `interview_recovery_attempts`.

## APIs

Recruiter (login required, scoped to the interview's recruiter):

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/interviews/<id>/recovery/reschedule-request` | Log a candidate's request (`reason`, optional `preferred_windows`) and start automation |
| POST | `/api/interviews/<id>/attendance` | `{"attendance": "attended" \| "no_show"}` |
| GET | `/api/interview-recovery/cases?status=ESCALATED` | List cases (comma-separated statuses) |
| GET | `/api/interview-recovery/cases/<case_id>` | Case incl. proposed slots and full history |
| POST | `/api/interview-recovery/cases/<case_id>/retry` | Restart an escalated case |
| POST | `/api/interview-recovery/cases/<case_id>/close` | Close a case |

`GET /api/interviews` now includes a `recovery` summary per interview (and no longer returns the candidate token).

Candidate (public, token in the URL; responses contain no emails, phone numbers or internal ids):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/interview-recovery/public/<token>` | Interview summary, case state, offered slots, allowed actions |
| POST | `/api/interview-recovery/public/<token>/reschedule` | Request a reschedule / share availability windows |
| POST | `/api/interview-recovery/public/<token>/respond` | `{"wants_reschedule": true \| false}` |
| POST | `/api/interview-recovery/public/<token>/confirm` | `{"slot_id": "YYYY-MM-DDTHH:MM"}`; returns 409 with fresh options if taken |

Scheduler: `GET|POST /api/interview-recovery/run` with `Authorization: Bearer <INTERVIEW_RECOVERY_CRON_SECRET or CRON_SECRET>`.

## Data

New MongoDB collections (created with indexes automatically at startup by `database._ensure_indexes`; no manual migration):

- `interview_recovery_cases`: id, interview_id, candidate_id, recruiter_id, jd_id, interviewer, recovery_type (`RESCHEDULE`/`NO_SHOW`), status, stage, source, reason, preferred_windows, attempt_count, max_attempts, delivery_failure_count, error_count, proposed_slots, unavailable_slots, selected_slot, confirmed_slot, original_interview_start, next_action_at, response_deadline, lease_until, last_error, escalated_at, escalation_reason, recommended_action, outcome, created_at, updated_at, closed_at.
- `interview_recovery_attempts`: append-only history (case_id, action, outcome, attempt_number, deliveries[{channel, status, provider_message_id, error, transient}], detail, created_at).
- `interview_recovery_locks`: short-lived booking locks (TTL index).

New optional fields on `interviews`: `candidate_access_token` (unique when present), `attendance_status`. New interview status value: `No Show`.

## Configuration

All settings are validated at use; invalid values return a clear 503 instead of silently changing behaviour. See `backend/.env.example` for the full list. Key ones:

| Variable | Default |
|---|---|
| `INTERVIEW_RECOVERY_ENABLED` | `true` (set `false` to switch everything off; existing interview features are unaffected) |
| `INTERVIEW_TIMEZONE` | `UTC`. **Set this** to the zone recruiters enter interview times in, e.g. `Asia/Kolkata`; no-show timing and slot hours depend on it |
| `INTERVIEW_NO_SHOW_DETECTION` | `confirmed` |
| `INTERVIEW_NO_SHOW_GRACE_MINUTES` | `15` |
| `INTERVIEW_RECOVERY_MAX_ATTEMPTS` | `3` |
| `INTERVIEW_RECOVERY_RESPONSE_TIMEOUT_MINUTES` | `1440` |
| `INTERVIEW_RECOVERY_RETRY_DELAY_MINUTES` | `60` |
| `CANDIDATE_TEST_BASE_URL` | required: public app URL used in candidate links |

## Deployment checklist

1. Set `CANDIDATE_TEST_BASE_URL` (public HTTPS URL of the app) and `INTERVIEW_TIMEZONE`.
2. SMTP (`SMTP_HOST/PORT/USER/PASS`, `DEFAULT_FROM_EMAIL`) must work; Twilio is optional (SMS is sent in addition to email when configured).
3. Set `INTERVIEW_RECOVERY_CRON_SECRET` (or rely on Vercel's `CRON_SECRET`).
4. Schedule the tick. Retries, response timeouts and auto no-show detection only advance when `/api/interview-recovery/run` is called. On Vercel **Pro**, add to `vercel.json`:
   ```json
   "crons": [{ "path": "/api/interview-recovery/run", "schedule": "*/10 * * * *" }]
   ```
   Vercel **Hobby** only allows daily crons (more frequent schedules fail deployment), so use an external scheduler (e.g. GitHub Actions or cron-job.org) calling the endpoint every 5–15 minutes with the bearer secret. Reschedule requests themselves do not wait for the tick.
5. Deploy; indexes are created on the first request.

## Not implemented / limitations

- **External calendars**: there is no Google/Microsoft calendar connection in HR Assist. Availability comes from interviews booked in HR Assist. `INTERVIEW_CALENDAR_PROVIDER` accepts only `internal`; adding one means implementing `CalendarProvider` (free/busy read and event update permissions). Calendar event updates are recorded as `not_configured`, never as success.
- **Interviewer notification**: interviewers are free-text names with no email, so the recruiter is asked (in-app) to inform them.
- **Inbound email/SMS replies** are not parsed; candidates respond through the manage link (or the recruiter logs the request).
- **Meeting-provider attendance** is not available; see the no-show detection modes above.
- Public token endpoints have no rate limiting (same as the existing assessment token endpoints).
