# Environment Notes

This file documents the practical quirks of this repository's working environment so future sessions do not waste time rediscovering them.

## 1. Repo and Deployment Model

- Primary workspace: Codespaces at `/workspaces/dev-rse`
- Git remote: `origin https://github.com/chrisj909/dev-rse`
- Default branch: `main`
- Vercel deploys from repo state on `main`, not from uncommitted Codespaces changes
- Supabase is the hosted database target

## 2. What Works From This Environment

- File edits, tests, commits, and pushes work normally from this Codespace
- `git push --dry-run origin main` succeeds from this environment
- Python virtual environment is at `/workspaces/dev-rse/.venv`
- Backend tests run successfully through `/workspaces/dev-rse/.venv/bin/python -m pytest`
- Frontend production builds run successfully from `frontend/`

## 3. Local Default Environment

Unless overridden explicitly in a shell command, this repo loads local dev values from `.env` at the repo root.

Typical local defaults in this workspace:

- `APP_ENV=development`
- `DATABASE_URL=postgresql+asyncpg://rse_user:rse_password@localhost:5432/rse_db`
- `DATABASE_SYNC_URL=postgresql://rse_user:rse_password@localhost:5432/rse_db`

Implication:

- any production check that depends on env vars must override both `DATABASE_URL` and `DATABASE_SYNC_URL`
- otherwise imports from `backend/app/core/config.py` or `backend/app/db/session.py` may still resolve to local DB values

## 4. Supabase Connectivity Quirk

The direct Supabase DB host for this project resolved to IPv6 from Codespaces and was not reachable from this environment.

Observed behavior:

- direct host `db.<project>.supabase.co:5432` failed from Codespaces with `Network is unreachable`
- pooler host `aws-1-us-east-1.pooler.supabase.com:6543` resolved to reachable IPv4 addresses

Practical rule:

- from this Codespace, use the Supabase pooler when running connection tests or Alembic checks
- do not assume the direct host is reachable from Codespaces even if it works from another machine

## 5. Alembic Notes

- Alembic is a shell/terminal tool, not SQL for the Supabase SQL editor
- this repo's Alembic env imports application settings, so production commands must override both:
  - `DATABASE_URL`
  - `DATABASE_SYNC_URL`
- current known good Alembic verification from Codespaces used the pooler host for both URLs

## 6. Scheduler Notes

- cron endpoint: `/api/cron/run-signals`
- Vercel cron cannot send custom `X-Cron-Secret` headers by default
- repo now supports bearer-token auth using `CRON_SECRET`
- `vercel.json` contains the scheduled cron entry

## 7. Operational Rhythm

- safe to let the agent handle code edits, tests, commits, and pushes directly
- pause only for:
  - Supabase SQL editor actions
  - Vercel UI/env changes when they cannot be done via repo code
  - credential rotation or secrets the user does not want pasted into commands

## 8. Current Important Commits

- `c501ac1` county-aware parcel identity and Jefferson support
- `3b7e14b` dashboard limit fix and Enter-to-apply search behavior
- `e1baea6` Vercel-compatible cron authentication
- `90acacb` documentation refresh and scoring roadmap