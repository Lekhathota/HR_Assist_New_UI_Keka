# Code Execution: Reference Solutions, Test Cases and Grading

HR Assist runs submitted code in two places:

| What | Where it runs | Needs setup? |
|---|---|---|
| SQL (reference queries and candidate answers) | In-memory SQLite inside the API, read-only authorizer, no file/ATTACH/PRAGMA/extension access, 3 s time limit, 1,000-row cap | No |
| Code (Python, JavaScript, Java, C, C++): reference solutions and candidate answers | **Judge0** sandbox, never on the HR Assist server | Yes: `JUDGE0_URL` |

Code is never executed on the application server. The server holds MongoDB, SMTP and OpenAI credentials, and Vercel functions offer no process isolation.

Results are never estimated or simulated. Until `JUDGE0_URL` is set:
- **Verify solution** reports **Execution unavailable** for coding questions, so **an assessment with coding questions cannot be approved or sent** (SQL questions are unaffected: SQLite runs in the API).
- Candidates cannot run code, and a submitted coding answer is recorded as an **Execution error (infrastructure)**: no marks and no pass/fail are decided, the assessment stays **COMPLETED (pending re-grade)**, and the hiring stage is not changed. Use **Re-grade** once execution is available.

## Recommended: self-hosted Judge0 CE (free, open source)

Judge0 runs each submission in an `isolate` sandbox with per-run CPU-time, wall-time and memory limits, process limits, and network disabled by default. No paid service is needed.

1. Create a small Linux VM (2 vCPU / 4 GB is enough to start) with Docker and Docker Compose. Judge0 needs cgroup v1; on newer Ubuntu releases add `systemd.unified_cgroup_hierarchy=0` to the kernel command line and reboot (see the Judge0 install notes).
2. Download a Judge0 CE release (`judge0-v1.13.x.zip`) from github.com/judge0/judge0/releases and unzip it.
3. Edit `judge0.conf`:
   - set `REDIS_PASSWORD` and `POSTGRES_PASSWORD`;
   - set `AUTHN_HEADER=X-Auth-Token` and `AUTHN_TOKEN=<long random string>`;
   - keep `ENABLE_NETWORK=false` (the default) so submissions have no network access;
   - optionally lower `MAX_CPU_TIME_LIMIT` / `MAX_MEMORY_LIMIT`.
4. `docker compose up -d db redis`, wait about 10 s, then `docker compose up -d`.
5. Put it behind HTTPS (for example a reverse proxy with a certificate) and allow inbound traffic only on that port.
6. In Vercel → Project → Settings → Environment Variables set:
   ```
   JUDGE0_URL=https://judge0.your-company.com
   JUDGE0_AUTH_TOKEN=<the AUTHN_TOKEN from judge0.conf>
   ```
   Redeploy.

Optional settings: `JUDGE0_CPU_TIME_LIMIT` (default 2 s), `JUDGE0_MEMORY_LIMIT_KB` (default 128000), and `JUDGE0_LANGUAGE_IDS` if your Judge0 build uses different language ids (defaults: python 71, javascript 63, java 62, c 50, cpp 54).

Hosted alternative: Judge0 on RapidAPI (`JUDGE0_URL=https://judge0-ce.p.rapidapi.com`, `JUDGE0_RAPIDAPI_KEY=...`). This is a paid or free-tier external service, so it is not the default recommendation.

## Coding Configuration (per question)

Hiring Pipeline → open a draft assessment → expand **Coding Configuration** on a coding or SQL question.

| Group | Settings |
|---|---|
| Question | Title, problem statement, skills/topics, difficulty, maximum marks; JD and client shown read-only; the recruiter prompt it was generated from |
| Requirements | Input format, output format, constraints, edge cases (shown to the candidate) |
| Execution (coding) | Allowed languages, CPU time limit per test (0.5–15 s), memory limit (16–512 MB), output comparison (`trim_trailing` default, `exact`, `tokens`); read-only compiler/runtime, entry point and run convention for each language |
| Reference solutions | A primary reference (any language) plus optional references in other languages. **Every** reference must pass every enabled test |
| Test cases | Public samples (visible) and hidden tests; per test: weight (0.01–100), mandatory, enabled |
| Scoring & qualification | Partial credit on/off, minimum tests passed, minimum score %, all mandatory tests must pass; a preview table shows marks per number of tests passed |

All settings are validated on the server (`assessment/code_execution/coding_config.py`). Saving re-verifies, and changing the reference, tests, limits, languages or comparison makes the previous verification stale.

A coding question is **publishable** only when it has a reference solution that was executed and passed every enabled test, at least one public and one hidden test, positive weights, valid limits and languages, and qualification thresholds that are achievable (for example, "minimum tests passed" cannot exceed the number of tests).

## Scoring

Marks come only from executing the candidate's program; the source is never compared with the reference.

- `marks = maximum marks × (weight of passed tests ÷ total weight)` with partial credit, or all-or-nothing without it. With 5 equal tests and 10 marks: 0, 2, 4, 6, 8, 10.
- Per question the result records the tests passed, marks, result status and qualification:

| Result | Meaning |
|---|---|
| Passed | Every test passed |
| Partially passed | Some marks earned, not every test |
| Not passed | No test passed (wrong output) |
| Execution error | Compile error, or every test crashed/timed out (the candidate's error, scored 0), or an **infrastructure** failure (retryable, no verdict) |
| Qualified / Not qualified | Whether the question's thresholds (min tests, min score %, mandatory tests) are met. Separate from Passed |

Statuses per test: passed, failed (wrong answer), compile_error, runtime_error, time_limit, memory_limit, output_limit. A Judge0 internal error is an infrastructure failure, never a candidate failure.

### Assessment score and pass decision

Assessment Settings → **Scoring & qualification**:
- **Section weights** (MCQ / Coding & SQL, adding up to 100%). Without weights the overall score is points earned ÷ points possible.
- **Minimum MCQ score** and **minimum coding score** (%).
- **Coding qualification is independent of MCQs**: when on, the coding minimum (and, if selected, every coding question's own qualification) must be met regardless of the MCQ score. When off, the coding minimum is advisory.

The assessment passes when the overall score reaches the passing score and every enabled requirement is met. The result stores the section scores, the weights applied and each requirement with its actual value.

## Lifecycle: Generate → Draft → Configure → Validate → Approve → Send

1. Questions are generated into a **draft**; nothing is sent automatically.
2. Configure and verify each coding question. **Validate** lists everything that blocks publishing.
3. **Approve for sending** records a fingerprint of the questions, tests and scoring rules. Any later change invalidates the approval.
4. **Send** requires a current approval and stores an immutable **published version** (`assessment_versions`) of the questions and scoring rules. Results record the version they were scored against.
5. A sent assessment is read-only. If the candidate has not started, **Edit questions (return to draft)** re-opens it (the link stops working until it is approved and sent again as version N+1; earlier versions are unchanged). Once started, nothing can change.

## Managing reference solutions and test cases

Hiring Pipeline → open an assessment → expand **Reference solution & test cases** on a coding or SQL question.

- **Reference solution:** choose the language (Python, JavaScript, Java, C, C++). Programs read stdin and print to stdout, and Java uses `public class Main`. SQL questions have a reference query, a schema, and a "row order matters" switch.
- **Test cases:** name, input (or SQL dataset), expected output, visible/hidden, enabled/disabled and description. Add, edit, delete and reorder are supported. Disabled tests are ignored for verification, grading and the candidate view.
- **Save & verify** stores the configuration and immediately runs the reference on every enabled test. For SQL, verification also records the expected result of each dataset by running the reference query.
- **Verify solution** re-runs verification on the saved configuration (allowed even after the assessment is sent).
- Editing is allowed only while the assessment is in DRAFT, so candidates who already have the link are never graded against tests that changed under them.

### Verification status

| Status | Meaning |
|---|---|
| Verified | The reference was executed and passed every enabled test case |
| Failed | It was executed and at least one enabled test failed or errored (per-test results are shown) |
| Execution unavailable | No sandbox is configured, or Judge0 was unreachable |
| Not verified | Never verified, or the solution, language, schema or any enabled test changed since the last verification |

Each verification stores a fingerprint of the reference, language, schema and enabled tests, so any change automatically turns the result back into **Not verified**. If a save lands while a verification is running, the stale result is discarded (HTTP 409, "verify again").

## API (recruiter, login required)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/assessment/execution-status` | Whether code / SQL execution is available, plus supported languages |
| GET | `/api/assessment/question/<id>/reference` | Reference solution, all test cases (including hidden), verification |
| PUT | `/api/assessment/question/<id>/reference` | Save `{reference_solution, reference_language, test_cases[], sql_schema?, order_matters?, verify?}` |
| POST | `/api/assessment/question/<id>/verify` | Execute the saved references against the enabled tests |
| GET | `/api/assessment/<id>/publish-check` | Problems that block approval, and the approval state |
| POST | `/api/assessment/<id>/approve` | Approve the validated draft for sending |
| POST | `/api/assessment/<id>/return-to-draft` | Re-open a sent, unstarted assessment for editing |
| GET | `/api/assessment/<id>/versions` | Published versions |
| GET | `/api/assessment/<id>/code-attempts` | Candidate runs and submissions (code, language, tests passed, marks) |

`PUT /api/assessment/question/<id>/reference` also accepts `config` (the Coding Configuration fields above) and per-test `weight` / `mandatory`. `PUT /api/assessment/<id>` accepts `scoring_policy`.

Candidate endpoints never return the reference solution, hidden or disabled tests, or verification data. Candidates see only enabled visible examples and the number of hidden tests.

## Data

Stored on the existing `questions` documents (no new collection, no migration):
- `correct_answer` (reference solution) and `reference_language`;
- `test_cases[]`: `id`, `name`, `description`, `hidden`, `enabled`, and either `input`/`expected_output` or `setup_sql` plus computed `expected`;
- `verification`: `status`, `results[]`, `message`, `verified_at`, `language`, `fingerprint`;
- `config_fingerprint`, used to discard verification results that would overwrite a newer save;
- configuration: `title`, `edge_cases`, `time_limit_seconds`, `memory_limit_mb`, `comparison`, `scoring`, `reference_solutions`; per test `weight` and `mandatory`.

On the assessment: `scoring_policy`, `approval`, `published_version`. Collections `assessment_versions` (published snapshots) and `assessment_code_attempts` (run/submit history). Results store section scores, qualification checks, `needs_retry` and `assessment_version`.

## Tests

`backend/tests/test_coding_engine.py` executes real Python, JavaScript and Java programs through `tests/local_runner.py`, a **test-only** subprocess backend with the Judge0 runner's interface (never used by the application). Set `JUDGE0_URL` to also run `LiveJudge0Tests` against your sandbox.

PowerShell is not supported: the Judge0 CE language set does not include it.
