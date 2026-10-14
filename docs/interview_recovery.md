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
No-show            ─► PENDING ─► outreach    ─► AWAITING_RESPONSE ─► "yes" ─► SLOT_PROPOSED ─► ... ─► RECOVERED
                                                                   └► "no"  ─► CLOSED (recruiter informed)
No slots / no reply / delivery failure ─► RETRY_SCHEDULED ─► ... ─► ESCALATED (recruiter notified once)
```
1. **Reschedule request** (candidate page or recruiter-logged) creates a case and runs the slot search *in the same request*, so options go out within seconds. No recruiter action.
2. **Slot search** uses the recruiter's booked interviews (and the candidate's other interviews), interview duration, working hours/days, minimum notice and any availability windows the candidate entered. It offers up to `SLOT_COUNT` slots spread across different days and never re-offers the current time or slots found to be taken.
3. **Confirmation** re-checks availability under a per-recruiter booking lock before updating the *existing* interview record (no duplicate interview). If the slot was taken meanwhile it is not booked; fresh options are shown instead.
4. **After booking**: candidate gets a confirmation email; the recruiter gets an in-app notification (informational, no action needed) and is asked to tell the interviewer, because interviewers are free-text names without contact details.
5. **No-show**: after `INTERVIEW_NO_SHOW_GRACE_MINUTES`, the interview is marked `No Show` and the candidate is emailed asking whether they want a new time (Yes → slot proposal flow, No → case closed, recruiter informed).
6. **Stops automatically** when the interview is cancelled, completed (Selected/Rejected), rescheduled by the recruiter, marked attended, or deleted.
### No-show detection
HR Assist has no attendance feed from a meeting provider, so a no-show is only ever acted on from an **explicit attendance outcome**. It is never inferred just because the scheduled time passed.
- After an interview's **scheduled end** + `INTERVIEW_NO_SHOW_GRACE_MINUTES`, the interviewer or recruiter clicks **Attended** or **No-show** on the interview (Hiring Pipeline → Interviews). The outcome is saved on the interview (`attendance_status`, `attendance_recorded_at`, `attendance_recorded_by`).
- **No-show** opens the recovery case and sends the follow-up immediately. The scheduled sweep (below) also picks up any interview recorded as a no-show that has no case yet: outcomes recorded late (within `INTERVIEW_NO_SHOW_LOOKBACK_HOURS`, default 7 days), or a request that failed midway.
- Never processed: interviews that are cancelled, completed (Selected/Rejected), rescheduled to a new time, marked attended, or still in progress or inside the grace period.
- `INTERVIEW_NO_SHOW_DETECTION=auto` (opt-in) additionally treats ended interviews with **no** recorded attendance as no-shows. Use it only if interviewers reliably click **Attended**.
- Idempotent: each interview occurrence (interview + original start time) gets at most one no-show case, enforced by a unique index on open cases. Concurrent sweeps cannot create a second case or send a second initial email.
### Follow-up email
Sent automatically through the existing SMTP integration (no-show follow-ups are email-only; reschedule requests retain optional Twilio SMS), using the interview's real data:
> Subject: Follow-Up Regarding Your Interview
> Hi {candidate name}, We noticed that you were unable to attend your scheduled interview for the {job title} position on {original date and time} ({INTERVIEW_TIMEZONE}). … choose a new interview time using the link below: {secure /interview/<token> link} … Best regards, {COMPANY_NAME} Talent Acquisition Team
The link is the existing candidate reschedule page. It is tokenized per interview, so a candidate can only view and manage their own interview. No-show recovery has a hard limit of 2 outreach emails total, including the initial follow-up: one initial email and at most one reminder. If the candidate has not responded or rescheduled by the configured retry interval, the system sends the reminder with the subject "Reminder: Follow-Up Regarding Your Interview". An email attempt is recorded with its delivery status and any failure reason. Confirmed transient delivery failures use bounded backoff and do not count as candidate outreach attempts; uncertain SMTP acceptance is not blindly resent. Once the candidate reschedules, declines, or a recruiter resolves the case, no further candidate outreach is sent. If the case remains unresolved after the second outreach attempt and its response window expires, automatic outreach stops and the case is escalated to the recruiter.
Each attempt is stored in `interview_recovery_attempts` with interview id, candidate id, attempt number, message type, timestamp, delivery status and failure reason. The case stores `detected_at`, `last_outreach_at`, `last_attempt_at`, `email_delivery_status` (`pending`, `sending`, `sent`, `failed`, `unknown`), and the next action/response deadline. Recruiter APIs expose `next_retry_at`; it is empty once two emails have been delivered or outreach has stopped. The Hiring Pipeline displays `1 of 2` or `2 of 2` beside the recovery status.
| Shown in Hiring Pipeline | Case status |
|---|---|
| No-show detected · outreach pending | PENDING / PROCESSING |
| Outreach pending (retrying) / Follow-up retry scheduled | RETRY_SCHEDULED |
| Outreach sent · awaiting reply | AWAITING_RESPONSE |
| Candidate choosing new time | SLOT_PROPOSED |
| Rescheduled | RECOVERED |
| Escalated to recruiter | ESCALATED |
| Resolved | CLOSED |
### Attempts, retries and escalation
| Situation | Counts as attempt? | What happens |
|---|---|---|
| No-show email delivered | yes | wait `INTERVIEW_NO_SHOW_RETRY_INTERVAL_MINUTES` (default 1440 / 24 hours); send one reminder, then allow the same response interval before escalation |
| Reschedule options delivered | yes | wait `RESPONSE_TIMEOUT_MINUTES` |
| No reply by the deadline | (the delivered message already counted) | resend fresh options / reminder, or escalate when `attempt_count >= MAX_ATTEMPTS` |
| Slot search finds nothing | yes for reschedule cases; separate bounded search counter for no-show cases | retry after `RETRY_DELAY_MINUTES`, escalate at the limit |
| Transient delivery failure (SMTP timeout etc.) | no (`delivery_failure_count`) | exponential backoff from `RETRY_DELAY_MINUTES` (max 24 h), escalate after `MAX_DELIVERY_FAILURES` |
| Permanent delivery failure (no email, SMTP not configured, link URL missing) | no | escalate immediately |
| Unexpected worker error | no (`error_count`) | retry later, escalate after `MAX_DELIVERY_FAILURES` |
| Slot taken during confirmation | no | new options offered immediately |
Escalation is idempotent (`escalated_at` is set atomically once): one in-app notification plus one email to the interview's recruiter, containing the interview/candidate reference, reason, recommended next step and attempt history. **Retry** on an escalated reschedule case resets the counters and allows a fresh escalation later. No-show cases cannot be restarted: recruiters must contact the candidate directly or close the case; **Close case** ends it.
### Reliability
- One open case per interview and type (partial unique index); duplicate clicks or detection runs reuse it.
- No-show cases are tied to the specific interview time, so re-running detection never re-contacts the candidate.
- Every scheduler action starts with an atomic claim that sets a lease (`INTERVIEW_RECOVERY_LEASE_SECONDS`). If a serverless invocation dies, the case is picked up after the lease expires. A booking interrupted after the interview was updated is completed, not re-booked.
- No-show email sends reserve a persistent dispatch marker atomically before SMTP. Concurrent ticks cannot reserve the same send. A crash or connection loss during submission leaves delivery uncertain and escalates for SMTP-log review instead of resending. SMTP has no idempotency API, so uncertain acceptance is never treated as a safe technical retry. Only confirmed failures use bounded exponential backoff; a failed QUIT after acceptance counts as sent.
- Candidate replies receive slot options on the existing portal; no additional automatic no-show or slot reminder email is sent. Successful booking retains the existing confirmation email.
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
- `interview_recovery_cases`: id, interview_id, candidate_id, recruiter_id, jd_id, interviewer, recovery_type (`RESCHEDULE`/`NO_SHOW`), status, stage, source, reason, preferred_windows, attempt_count, max_attempts, delivery_failure_count, error_count, proposed_slots, unavailable_slots, selected_slot, confirmed_slot, original_interview_start, next_action_at, response_deadline, lease_until, last_error, last_attempt_at, last_outreach_at, email_delivery_status, outreach_dispatch, slot_search_count, escalated_at, escalation_reason, recommended_action, outcome, created_at, updated_at, closed_at.
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
| `INTERVIEW_RECOVERY_MAX_ATTEMPTS` | `3` (reschedule cases only; no-show email limit is always `2`, including existing cases) |
| `INTERVIEW_NO_SHOW_RETRY_INTERVAL_MINUTES` | `1440` (24 hours) |
| `INTERVIEW_RECOVERY_RESPONSE_TIMEOUT_MINUTES` | `1440` |
| `INTERVIEW_RECOVERY_RETRY_DELAY_MINUTES` | `60` |
| `CANDIDATE_TEST_BASE_URL` | required: public app URL used in candidate links |
## Deployment checklist
1. Set `CANDIDATE_TEST_BASE_URL` (public HTTPS URL of the app) and `INTERVIEW_TIMEZONE`.
2. SMTP (`SMTP_HOST/PORT/USER/PASS`, `DEFAULT_FROM_EMAIL`) must work; Twilio is optional (SMS is sent in addition to email when configured).
3. Set `INTERVIEW_RECOVERY_CRON_SECRET` (or rely on Vercel's `CRON_SECRET`).
4. Schedule the tick. Retries, response timeouts and the no-show sweep advance only when `/api/interview-recovery/run` is called. Two schedulers are included:
   - **GitHub Actions** (`.github/workflows/interview-recovery.yml`) runs every 15 minutes on any Vercel plan. Add repository secrets `INTERVIEW_RECOVERY_RUN_URL` (e.g. `https://shimentoxtalentos.vercel.app/api/interview-recovery/run`) and `INTERVIEW_RECOVERY_CRON_SECRET` (same value as in Vercel). Until both are set the workflow skips with a warning.
   - **Vercel Cron** (`vercel.json`) runs once a day at 06:00 UTC as a backstop; Hobby plans allow daily crons. Vercel sends `CRON_SECRET` automatically when that variable is set in the project.
5. Deploy; indexes are created on the first request.
## Not implemented / limitations
- **External calendars**: there is no Google/Microsoft calendar connection in HR Assist. Availability comes from interviews booked in HR Assist. `INTERVIEW_CALENDAR_PROVIDER` accepts only `internal`; adding one means implementing `CalendarProvider` (free/busy read and event update permissions). Calendar event updates are recorded as `not_configured`, never as success.
- **Interviewer notification**: interviewers are free-text names with no email, so the recruiter is asked (in-app) to inform them.
- **Inbound email/SMS replies** are not parsed; candidates respond through the manage link (or the recruiter logs the request).
- **Meeting-provider attendance** is not available; see the no-show detection modes above.
- Public token endpoints have no rate limiting (same as the existing assessment token endpoints).
