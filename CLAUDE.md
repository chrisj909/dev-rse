# CLAUDE.md — Real Estate Signal Engine (RSE)

Project context and workflow guide for AI assistants. Read this before making any changes.

## What this project is

A lead generation system for Alabama real estate investors. It ingests parcel records from Shelby and Jefferson county ArcGIS services, derives seller-distress signals, scores each parcel across three lenses (broad / owner_occupant / investor), and exposes the results through a FastAPI backend and a Next.js dashboard.

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

### Leaflet / map
Map uses `react-leaflet@4` (v4, not v5 — v5 requires React 19). Dynamic import with `{ ssr: false }` is required. Leaflet CSS is imported at the top of `globals.css`.

## Backend patterns

### Ingest pipeline
`POST /api/ingest/run` → scrape ArcGIS → upsert properties → run SignalEngine → TaxDelinquencyService → ScoringEngine (all 3 modes). Each layer uses `session.begin_nested()` savepoints so one bad property doesn't abort the batch. Deadlocks retry 3× with exponential backoff.

### ArcGIS scraper
Both Shelby and Jefferson scrapers request `returnGeometry=true&outSR=4326` to get WGS84 polygon geometry. `_centroid_from_geometry()` in `arcgis_scraper.py` computes the polygon centroid and returns `(lat, lng)`. Properties without geometry get `null` coords.

### Scoring modes
Three modes stored separately in the `scores` table (one row per `property_id × scoring_mode`): `broad`, `owner_occupant`, `investor`. All three must be populated for the lens selector to show meaningful data. Use the Rescore tool on the ingest page after a fresh ingest.

### Cron / rescore
`GET /api/cron/run-signals` processes 500 properties per call. Protected by `CRON_SECRET` (Bearer token, `X-Cron-Secret` header, or `?cron_secret=` query param). Returns JSON `{status, has_more, next_offset, total_properties}` — never a bare 500.

### Response models
`LeadResponse` and `PropertyDetailResponse` are in `backend/app/models/responses.py`. Both include `lat` and `lng` (nullable float). If you add a new field to the ORM model, add it here and wire it through `_build_lead()` / `_build_property_detail_response()` in `leads.py`.

## Frontend routes

| Route | Component | Notes |
|-------|-----------|-------|
| `/` | `app/page.tsx` | Dashboard, auto-refreshes 60s |
| `/leads` | `app/leads/page.tsx` + `components/LeadsTable.tsx` | Server page passes data to client component |
| `/map` | `app/map/page.tsx` | Client-only, Leaflet dynamic import |
| `/property` | `app/property/page.tsx` | `?parcel_id=&county=&scoring_mode=` |
| `/lists` | `app/lists/page.tsx` | Client-only, Supabase browser client |
| `/auth` | `app/auth/page.tsx` | Sign in / sign up |
| `/ingest` | `app/ingest/page.tsx` | Ingest runner, rescore, DB status |

## Vercel deployment

- Git push to `main` → auto-deploy
- `/api/*` routes → Python FastAPI via `api/index.py` (Mangum)
- All other routes → Next.js frontend under `frontend/`
- Cron: daily at 06:00 UTC → `GET /api/cron/run-signals`
- Env vars are set in Vercel dashboard. Frontend needs `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

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
