# Authentication + RBAC integration patch

This patch targets the uploaded `HR_Automation_New_UI_CLEAN` project.

## Files in this patch

- `backend/security/rbac.py` (new): centralized API role policy and role-name normalization.
- `backend/security/__init__.py` (new): package marker.
- `backend/app.py` (changed): installs centralized API role enforcement.
- `backend/services/auth_service.py` (changed): normalizes current user's role and adds a reusable `role_required` decorator.
- `backend/routes/auth_routes.py` (changed): returns only safe user fields from login and adds `GET /api/me`.
- `frontend/src/App.jsx` (changed): blocks restricted SPA pages based on the cached role.
- `frontend/src/pages/Login.jsx` (included unchanged): existing login stores the role returned by backend.

## Permission behavior

- Admin: unrestricted.
- Recruiter: dashboard/profile, jobs, candidate/resume workflows, matching, and interviews; no clients/vendors/reports/admin settings.
- Hiring Manager: dashboard/profile, candidate read/profile, interview read and limited review/approval actions; no job creation/deletion or administrative modules.

The route policy allows only `/outcome`, `/review`, or `/approve` POST interview paths to managers. If the app's actual approval action uses a different URL, add that exact route to `backend/security/rbac.py` after confirming its meaning.

## Install

1. Back up your project or commit the current working tree.
2. Copy the patch files into the same relative paths in your project, overwriting only the files marked changed and adding the new security files.
3. Confirm `.env` has a stable, secret `SECRET_KEY`; do not commit `.env`.
4. Restart Flask and rebuild React:
   - backend: restart using your existing backend command.
   - frontend: run `npm run build` in `frontend/` and copy the build output as your current README/deployment process requires.
5. Sign out and sign in again so `localStorage` refreshes the role.

## Test checklist

- Log in as each role.
- As Recruiter, verify jobs/talent/interviews work and clients/vendors/workflow admin return 403 from API.
- As Hiring Manager, verify candidates can be viewed and review actions work; verify job create/delete and admin-only modules return 403.
- As Admin, verify all modules remain accessible.
- Call a protected API without a token: it should return 401 (not 403).

## Important limitation

The frontend route guard is usability only. Backend authorization is the security boundary. This patch applies role restrictions centrally to API routes, but record-level ownership/assignment filtering (e.g., ensuring a hiring manager sees only their assigned candidates) must be enforced in the relevant query/service functions. The current project data model must be checked to determine how assignments are represented before safely implementing that filter. Do not treat hiding a page as data security.
