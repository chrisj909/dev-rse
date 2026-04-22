# CLAUDE.md — Real Estate Signal Engine (RSE)

Project context and workflow guide for AI assistants. Read this before making any changes.

## What this project is

A lead generation system for Alabama real estate investors. It ingests parcel records from Shelby and Jefferson county ArcGIS services, derives seller-distress signals, stores score modes for internal/admin workflows, and exposes a signal-first search experience through a FastAPI backend and a Next.js dashboard.

Deployed at: **https://dev-rse.vercel.app**

## Stack at a glance

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15 App Router, React 18, Tailwind CSS |
| Backend | FastAPI, SQLAlchemy 2 async, Mangum (Vercel adapter) |
| Database | PostgreSQL via Supabase (project ID: `ymddycgifjqmmqkojupf`) |
| Auth | Supabase Auth — email/password |
| Deployment | Vercel — auto-deploys on push to `main` |
| Migrations | Alembic (local/CI) — but use Supabase MCP for production |

## Repository layout

```
api/                  Vercel Python entry point (imports backend app)
backend/
  app/
    api/              FastAPI routes: ingest.py, leads.py, cron.py, health.py, export.py
    models/           SQLAlchemy ORM + Pydantic response models
    scrapers/         ArcGIS + GovEase scrapers
    scoring/          ScoringEngine + weights
    signals/          SignalEngine
    services/         TaxDelinquencyService
  alembic/versions/   DB migration scripts (0001–0005 so far)
  tests/              pytest suite (~573 tests)
frontend/
  app/                Next.js App Router pages
  components/         Shared React components
  hooks/              usePropertyLists, useSavedSearches
  contexts/           AuthContext (Supabase Auth)
  lib/                api.ts (getClientApiBaseUrl), supabase.ts, exportCsv.ts
```

## Running things locally

```bash
# Backend
cd backend
pip install -r requirements.txt
python main.py              # FastAPI on :8000

# Frontend
cd frontend
npm install
npm run dev                 # Next.js on :3000

# Tests
cd backend && python -m pytest tests/ -q
cd frontend && npm test         # map/data guardrail tests
cd frontend && npm run build    # type-check + build

# Local DB (Docker)
docker compose -f infra/docker-compose.yml up -d db
alembic upgrade head
```

## Database changes — IMPORTANT

**Alembic** is a migration version tracker. It stores which SQL scripts have already run in an `alembic_version` table and runs only new ones in order. Use it locally. For **production Supabase**, apply the SQL directly:

- Use the **Supabase MCP tool** (`mcp__claude_ai_Supabase__apply_migration`) — preferred, runs DDL safely
- Or paste into the Supabase SQL editor at `https://supabase.com/dashboard/project/ymddycgifjqmmqkojupf`
- Always also write the equivalent Alembic migration file in `backend/alembic/versions/` so local dev stays in sync

Current schema version: **0005** (`add_lat_lng_to_properties`)

## Supabase — key facts

- **Project ID**: `ymddycgifjqmmqkojupf` (region: us-east-1)
- **RLS on user tables**: `saved_searches`, `property_lists`, `property_list_items` — users can only read/write their own rows
- **RLS on shared tables**: `properties`, `signals`, `scores` have `SELECT USING (true)` (public read) so the browser Supabase client can join against them from user-data queries
- **`property_list_items` has NO FK to `properties`** — stores `county` + `parcel_id` only. PostgREST joins (`properties!inner`) do not work. Always use explicit multi-step queries: fetch items → fetch properties via `.in('parcel_id', [...])` grouped by county → fetch scores by property UUID
- **Auth redirect URL** must be set to `https://dev-rse.vercel.app` (not localhost) in Supabase Auth → URL Configuration for production email confirmations

## Frontend patterns

### API calls from client components
Always use `getClientApiBaseUrl()` from `@/lib/api` — **never** `process.env.NEXT_PUBLIC_API_URL` directly. In the browser it returns `window.location.origin`, which works on Vercel without any env var.

```ts
import { getClientApiBaseUrl } from '@/lib/api';
const res = await fetch(`${getClientApiBaseUrl()}/api/leads?...`);
```

### Auth
`AuthContext` wraps the whole app (`frontend/app/layout.tsx`). Use `useAuth()` to get `user`, `signIn`, `signUp`, `signOut`. The Supabase browser client is in `frontend/lib/supabase.ts`.

### User data hooks
- `usePropertyLists()` — lists CRUD, `addToList`, `addManyToList` (batch), `getListItems`, `removeFromList`, `exportList`
- `useSavedSearches()` — searches CRUD, `save(name, filters)`, `exportSearch`

### Signal-first lead search
`/leads` is now the primary search workflow. `components/LeadsTable.tsx` supports explicit `signals`, `exclude_signals`, and `signal_match` query params so operators can require or exclude each individual distress/ownership signal directly. Signal metadata and query parsing live in `frontend/lib/signalFilters.ts`.

### Saved views across map and leads
Saved searches are shared between `/map` and `/leads`. Map views persist the shared search filters plus `map_lat`, `map_lng`, and `map_zoom`; the map page reads those query params back in, preserves signal filters from `/leads`, and the map's List View handoff carries the same search criteria back into the lead builder.

### Campaign exports
Use the shared export helper in `frontend/lib/leadExport.ts` for lead exports. It paginates through `/api/leads` in 250-record pages, preserves active filters, and writes campaign-ready CSV rows including mailing address and active signals. Saved-search exports should call this helper; list exports should include mailing fields and signal summaries for direct-mail workflows.

### Leaflet / map
Map uses `react-leaflet@4` (v4, not v5 — v5 requires React 19). Dynamic import with `{ ssr: false }` is required. Leaflet CSS is imported at the top of `globals.css`.

## Backend patterns

### Ingest pipeline
`POST /api/ingest/run` → scrape ArcGIS → upsert properties → run SignalEngine → TaxDelinquencyService → CodeViolationService → ScoringEngine (all 3 modes). Each layer uses `session.begin_nested()` savepoints so one bad property doesn't abort the batch. Deadlocks retry 3× with exponential backoff.

### Code violation signal

`CodeViolationService` (`backend/app/services/code_violation_service.py`) matches properties against Birmingham 311 open data. The scraper (`backend/app/scrapers/birmingham_311_scraper.py`) fetches from the Birmingham CKAN API (`data.birminghamal.gov`, resource `9d55626a-afb2-4473-a084-cb70e721af23`), paginates all records, filters to violation case types, and returns a set of normalized street addresses. Only runs for Jefferson county or "all" ingests. The 311 data covers Birmingham city limits only — Shelby county properties will never match.

### Adding new signal data sources

Follow the `TaxDelinquencyService` / `CodeViolationService` pattern:

1. Scraper in `backend/app/scrapers/` fetches and normalizes data → returns matching keys (addresses, parcel IDs, etc.)
2. Service in `backend/app/services/` receives properties + scraped data, bulk-upserts only its signal column via `on_conflict_do_update(set_={signal_col: excluded.signal_col})`
3. Wire into `ingest.py` after `tax_service.ingest_batch()` and before scoring
4. The stub in `signals/engine.py` stays `return False` — the DB value written by the service is what scoring reads

### ArcGIS scraper
Both Shelby and Jefferson scrapers request `returnGeometry=true&outSR=4326` to get WGS84 polygon geometry. `_centroid_from_geometry()` in `arcgis_scraper.py` computes the polygon centroid and returns `(lat, lng)`. Properties without geometry get `null` coords.

### Scoring modes
Three modes are still stored separately in the `scores` table (one row per `property_id × scoring_mode`): `broad`, `owner_occupant`, `investor`. Treat these as backend/admin datasets rather than user-facing UI lenses. Use the Rescore tool on the ingest/admin page after a fresh ingest.

If `/api/health/stats` shows only `broad` counts, treat owner-occupant and investor data as incomplete and keep operators on signal-based searches until those score tables are repopulated. The same endpoint now also reports `score_schema.property_mode_unique_constraint`; if that is false, production is missing the unique constraint needed to upsert one score row per property and mode.

### Cron / rescore
`GET /api/cron/run-signals` processes 500 properties per call. Protected by `CRON_SECRET` (Bearer token, `X-Cron-Secret` header, or `?cron_secret=` query param). Returns JSON `{status, has_more, next_offset, total_properties}` — never a bare 500.

### Response models
`LeadResponse` and `PropertyDetailResponse` are in `backend/app/models/responses.py`. Both include `lat` and `lng` (nullable float). If you add a new field to the ORM model, add it here and wire it through `_build_lead()` / `_build_property_detail_response()` in `leads.py`.

## Frontend routes

| Route | Component | Notes |
|-------|-----------|-------|
| `/` | `app/page.tsx` | Dashboard, auto-refreshes 60s |
| `/leads` | `app/leads/page.tsx` + `components/LeadsTable.tsx` | Server page passes data to client component; primary custom search/save/export workflow |
| `/map` | `app/map/page.tsx` | Client-only, Leaflet dynamic import; saved views round-trip through shared search filters and hand off cleanly to `/leads` |
| `/property` | `app/property/page.tsx` | `?parcel_id=&county=` |
| `/lists` | `app/lists/page.tsx` | Client-only, Supabase browser client |
| `/auth` | `app/auth/page.tsx` | Sign in / sign up |
| `/ingest` | `app/ingest/page.tsx` | Admin console for ingest, rescore, DB status, and score coverage verification |

## Vercel deployment

- Git push to `main` → auto-deploy
- `/api/*` routes → Python FastAPI via `api/index.py` (Mangum)
- All other routes → Next.js frontend under `frontend/`
- Cron: daily at 06:00 UTC → `GET /api/cron/run-signals`
- Env vars are set in Vercel dashboard. Frontend needs `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

### Vercel plugin for Claude Code

The [Vercel plugin](https://vercel.com/docs/agent-resources/vercel-plugin) is installed at user scope (`npx plugins add vercel/vercel-plugin`). It auto-injects context for Next.js/Vercel projects at session start.

Useful slash commands:

| Command | Purpose |
| ------- | ------- |
| `/vercel-plugin:status` | Recent deployments, environment overview |
| `/vercel-plugin:deploy` | Trigger a preview deploy |
| `/vercel-plugin:deploy prod` | Trigger a production deploy |
| `/vercel-plugin:env` | List, pull, add, or diff environment variables |

Relevant skills to invoke on demand: `nextjs`, `deployments-cicd`, `vercel-functions`, `routing-middleware`, `env-vars`.

To reinstall: `npx plugins add vercel/vercel-plugin` (requires Bun — install via `curl -fsSL https://bun.sh/install | bash`).

## Common gotchas

1. **0 results on map** — check that `getClientApiBaseUrl()` is used, not `NEXT_PUBLIC_API_URL`
2. **List items show 0 properties** — no FK between `property_list_items` and `properties`; use explicit queries, not PostgREST joins
3. **500 after adding a model field** — run the DB migration (Supabase MCP or SQL editor) before deploying code that selects the new column
4. **Rank sort shows C first** — rank `asc` is A→C (correct for leads). `toggleSort` defaults rank to `asc` on first click
5. **Leaflet blank on SSR** — always dynamic-import `PropertyMap` with `{ ssr: false }`
6. **react-leaflet version** — must stay at v4. v5 requires React 19 which this project doesn't use
7. **Supabase email confirmations go to localhost** — Auth → URL Configuration → Site URL must be set to the Vercel URL, not localhost
8. **PgBouncer / asyncpg** — Supabase uses connection pooling. `config.py` auto-detects pooled URLs and disables asyncpg prepared-statement caching. Don't change this
9. **Multi-step ingest** — the frontend auto-batches in 250-record chunks. Full county ingest = many batches. Progress is cumulative
10. **Parcel IDs are county-scoped** — always store and pass both `county` and `parcel_id` together; parcel IDs repeat across counties
11. **Map lead fetch limit** — `/api/leads` caps `limit` at 250. If map requests 500 it will receive a 422 and show no leads. Use offset pagination.
12. **Owner/investor score rows are empty** — check `/api/health/stats`. If only `broad` counts exist, the data is incomplete; keep score health on `/ingest` and use signal-based searches in `/leads` and `/map`.
13. **Signal filters in saved searches** — per-signal include/exclude rules serialize through `signals` and `exclude_signals`. Keep both when building custom links or exports from saved searches.

## Functional recommendations (current priority)

- Map data loading: Keep map lead requests paginated at `limit=250` and iterate by `offset` until all records are retrieved. Always check `res.ok` before `res.json()` so API validation errors render clearly in the UI.

- Map resiliency UX: Show a visible error banner on map fetch failure and retain filter state. Keep mapped vs total counts in the header so operators can quickly spot missing coordinates.

- Signal-first workflow: Prefer building saved searches from explicit `signals` + `signal_match` filters in `/leads`. Treat `/map` as a visualization of those same filters, not a separate lens system.

- Score health visibility: Keep score coverage and schema diagnostics on `/ingest`. The dashboard, leads, and map should stay focused on search and review, not operational warnings.

- Export readiness: Lead and list exports should stay mailing-campaign-friendly by including mailing address plus a readable active-signal summary.

- High-volume map performance: If lead volume grows further, move from “fetch all pages” to viewport-based loading (`bounds` query params), then cluster markers.

- Functional guardrail tests: Keep frontend map data-load tests for the 250 API cap and non-200 response handling green (see `frontend/lib/mapLeads.test.ts`).

- Ingest-to-map freshness check: After full ingest/rescore, verify `/api/health/stats` and `/api/leads` counts match expected growth before map QA sign-off.
