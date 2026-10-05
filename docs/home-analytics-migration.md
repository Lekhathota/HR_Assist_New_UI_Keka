# Home and Reports frontend redesign

## Scope

The latest attached request limits this pass to the frontend. Existing local login,
proxy, backend port and additive backend analytics changes were preserved. No backend
code, credentials, database records or role policies were edited in this pass.
Main was fast-forwarded from ca391f5 to fb6f025 before continuing, preserving local work.

## Feature-preservation map

| Existing capability | Final location |
| --- | --- |
| Welcome greeting and role-filtered shortcuts | Home header and quick actions |
| Candidate screening metrics | Home KPI cards/pipeline; Reports overview |
| Recent candidates, comparisons and jobs | Home Recent Activity |
| Upcoming interviews | Home, using existing interviews response envelope |
| Detailed job performance | Reports: Job Analysis |
| Operational job, submission, interview, bench, vendor and shortage totals | Reports: Job Analysis, expandable all-time details |
| Team search, row limit and report table | Reports: Job Analysis, operational details |
| Screening conversion | Reports: Hiring Overview |
| Candidate statuses, sources and scores | Reports: Candidate Analytics |
| Existing skill gaps | Reports: Skill Gap Analysis, explicitly all time |
| PDF, DOCX, CSV and email | Reports: existing export dialog and handlers |
| Existing modules and role visibility | Shared sidebar and account area |
| Account, logout, command palette and recruiter chat | Existing shared controls |
| Old /dashboard bookmarks | Protected redirect to /welcome |

Unsupported efficiency, hire and period-comparison estimates are not presented as
measurements. No empty Time to Hire or Recruiter Performance tabs remain.

## Data contracts and definitions

The UI requests the original /api/dashboard, /api/reports, /api/interviews and
/api/jds URLs without new backend analytics parameters. Operational details retain
/api/dashboard/team. One frontend adapter supplies equivalent candidate totals to
Home and Reports. Optional failures are disclosed; primary failures show retry,
never sample data. This frontend does not require the earlier analytics API extension.

Default scope is all time. Optional date filters use candidate upload dates and
browser-local midnight, inclusive through the next day's midnight exclusive. Job
filters use primary JD relationships. Missing dates are excluded from dated views
with coverage notes. Filtering requires loaded candidate records.

Candidate counts deduplicate IDs. Screened is the union of recorded Selected and
Rejected outcomes. These are branches, not sequential hiring stages. Selected does
not imply Hired. Operational totals retain existing all-time API definitions.
Interview cards count events, not inferred completed interviews. Filtered Home
interviews use the current user's scheduled events. Upcoming appointments honor the
job filter and remain visible regardless of the candidate date filter.

Sources use stored candidate_source values or Unknown. When sources are absent,
recorded statuses supply the donut. Trends use actual candidate upload dates, never
invented stage history or growth percentages. Skills remain the existing all-time
report. Exports use displayed filtered data and label all-time skills separately.

## Visual implementation

Shared indigo/lavender tokens, white cards, compact tables and controls style existing
modules. Home has four KPI cards, three accessible SVG charts and activity/interview
panels. Reports has four supported tabs and compact filters. Existing keyboard,
focus and reduced-motion support remain. No chart dependency was added.

## Verification

48 frontend tests pass across eight suites: route guards/redirects, role navigation,
logout, original API contracts, local date/job filters, duplicate/missing data,
interview fields, errors/retry, keyboard tabs and mocked report export/email behavior.
No real emails or record mutations were used.

The in-app browser reports no available connections. Responsive visual inspection
and real-browser module smoke tests remain unverified. CSS review and component tests
do not replace these checks.

Production frontend build passed using a temporary output directory, preserving tracked build artifacts. The existing unused apiPut import warning in UserManagement.jsx remains. git diff --check passed.

## Alignment refinement

Aligned Home, Reports and Analyze to the shared content gutter, raised small labels
to a readable 12–14px scale and unified Analyze step/action colors. Analytics tables
now override the legacy 600px minimum width. Horizontal charts keep full HTML labels
with SVG bars; zero outcomes have zero-width bars. Single-month charts center the
recorded point and explain that more history is needed. Added regression coverage
for both sparse-data cases; 50 frontend tests pass. Browser visual QA remains pending.

## Application spacing audit

Reviewed the page roots and styles for Home, Reports, Jobs/list/create/details,
Talent/profile, Analyze, Hiring Pipeline, Clients/create/project, Vendors,
User Management, Workflow Admin, Profile, Login and both assessment screens.
Removed nested outer padding from shell pages; shortened 32–44px form section
margins, large empty/loading states, profile padding and forced client card heights.
Reduced analytics plot reserves while retaining matching chart heights. The Home
activity/interviews row no longer stretches an empty appointments card to match
all activity rows. Login viewport centering, editor heights, assessment footer
clearance and usable control dimensions were retained. These are CSS-only changes.
52 frontend tests passed. Actual page-by-page browser visual QA remains pending.

## Filter redesign

Home and Reports now share searchable multi-job checkbox selection, recorded status
and source selectors, and a compact date preset/custom-date menu. Jobs combine as a
union; candidate status/source narrow the resulting cohort. Filter options come from
the full loaded snapshot so selections do not erase other available choices. Clear
all restores the default. Menus support Escape, outside-click dismissal and one open
menu at a time. Report text/export content identifies selected jobs and segments.
Candidate-linked interviews honor job/status/source; future appointments are still
independent of candidate upload date. Job activity is hidden under candidate segment
filters. All-time skill and operational reports retain their explicit scope.
56 frontend tests passed, including multi-job interaction, combined segment filtering,
empty intersections and export filter labels. Backend and stored records are unchanged.
