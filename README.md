# Real Estate Signal Engine

Real Estate Signal Engine (RSE) is a lead generation system for public real estate data. It ingests county parcel records and tax-delinquency overlays, derives seller-investor signals, scores each parcel, and exposes the results through a FastAPI backend and a Next.js dashboard.

This document is the current solution design reference for the repository as it exists now.

## 1. Purpose

The system is designed to answer one question:

Which properties in the covered Alabama counties look most likely to represent actionable seller or investor opportunities?

The current MVP focuses on:

- ingesting parcel data from Shelby County ArcGIS and Jefferson County ArcGIS
- overlaying delinquency signals where available
- computing repeatable signal flags and a weighted lead score
- surfacing ranked leads in a browser UI and JSON APIs

## 2. Current Scope

Implemented now:

- live ingest from Shelby County ArcGIS
- live ingest from Jefferson County ArcGIS
- optional delinquent-only ingest mode
- property upsert keyed by `(county, parcel_id)`
- signal generation for absentee ownership and long-term ownership
- Shelby tax-delinquency ingestion path
- weighted lead scoring and rank assignment
- leads list, recent leads, property detail, CRM export, and cron APIs
- web dashboard, ingest UI, leads UI, and property detail UI
- Vercel deployment with FastAPI serverless API and Next.js frontend

Not fully realized yet:

- richer distress data sources beyond the current parcel and tax overlay set
- deeper ranking calibration for production-quality prioritization
- robust production-grade scheduled orchestration and monitoring
- final UX polish for filtering, pagination, and operator workflows

## 3. System Overview

```text
Shelby ArcGIS + Jefferson ArcGIS + Shelby GovEase overlay
      |
      v
     Ingest API / Scrapers
      |
      v
   properties table
      |
      +--> SignalEngine --> signals table
      |
      +--> TaxDelinquencyService
      |
      +--> ScoringEngine --> scores table
      |
      v
   FastAPI read APIs
      |
      v
   Next.js dashboard and lead views
```

## 4. Architecture

### 4.1 Runtime Topology

| Layer | Implementation | Notes |
| --- | --- | --- |
| Frontend | Next.js 15 + React 18 + Tailwind | Lives under `frontend/` |
| Backend API | FastAPI | Lives under `backend/` |
| Serverless adapter | Mangum | Wraps FastAPI for Vercel Python runtime |
| ORM | SQLAlchemy 2 async | Async engine, async sessions |
| Database | PostgreSQL | Docker locally, Supabase in hosted environments |
| Migrations | Alembic | Uses sync database URL |
| Deployment | Vercel | `/api/*` to Python, non-API routes to frontend |

### 4.2 Repository Layout

```text
api/                 Vercel Python entry point
backend/             FastAPI app, models, services, tests, scripts
frontend/            Next.js application
infra/               Local Docker Compose for Postgres
data/                Sample CSVs for test/dev workflows
vercel.json          Deployment routing config
.env.example         Environment template
```

### 4.3 Main Backend Components

| Component | Path | Responsibility |
| --- | --- | --- |
| App entry | `backend/main.py` | FastAPI app wiring, CORS, router registration |
| Config | `backend/app/core/config.py` | Env loading, DB URL normalization, PgBouncer-safe asyncpg config |
| DB session | `backend/app/db/session.py` | Async engine, session factory, NullPool serverless setup |
| Ingest API | `backend/app/api/ingest.py` | Scrape, upsert, signal run, tax update, score run |
| Leads API | `backend/app/api/leads.py` | Lead list, recent leads, property detail |
| Export API | `backend/app/api/export.py` | CRM export endpoints |
| Cron API | `backend/app/api/cron.py` | Protected batch signal + scoring endpoint |
| Scrapers | `backend/app/scrapers/` | ArcGIS and GovEase ingestion logic |
| Signals | `backend/app/signals/engine.py` | Signal generation pipeline |
| Scoring | `backend/app/scoring/engine.py` | Score and rank generation |

### 4.4 Main Frontend Views

| Route | Purpose |
| --- | --- |
| `/` | Dashboard summary and top leads |
| `/ingest` | Manual ingest runner |
| `/leads` | Searchable leads table |
| `/property?parcel_id=...` | Property detail view |

Note: property detail navigation currently uses the query-parameter route above because it is the most stable deployment path with the current Vercel setup.

## 5. Data Flow

### 5.1 Ingest Flow

1. `POST /api/ingest/run` triggers ArcGIS and optional overlay scrapers.
2. Results are merged by `parcel_id`.
3. Properties are upserted into the `properties` table.
4. Signal generation runs for the updated properties.
5. Tax-delinquency records are updated.
6. Scoring runs and writes rank and reason metadata.
7. The API returns a summary of fetched, upserted, signaled, and scored records.

### 5.2 Read Flow

1. Frontend pages call the FastAPI endpoints under `/api/*`.
2. Leads endpoints join `properties`, `signals`, and `scores`.
3. The API returns normalized response models.
4. The dashboard and lead feed render sorted slices of those results.

### 5.3 Scheduled Flow

`GET /api/cron/run-signals` is a protected endpoint that re-runs signal and scoring logic over existing properties.
The deployed Vercel cron calls this route daily using `CRON_SECRET` bearer authentication.

## 6. Core Data Model

### 6.1 `properties`

Canonical parcel record keyed by `(county, parcel_id)`.

Important fields:

- `county`
- `parcel_id`
- `address`
- `raw_address`
- `city`, `state`, `zip`
- `owner_name`
- `mailing_address`
- `raw_mailing_address`
- `last_sale_date`
- `assessed_value`

### 6.2 `signals`

Boolean flags derived from property and owner characteristics.

Current signal fields in active use:

- `absentee_owner`
- `long_term_owner`
- `tax_delinquent`
- `pre_foreclosure`
- `probate`
- `eviction`
- `code_violation`

### 6.3 `scores`

Weighted output of the scoring pipeline.

Important fields:

- `score`
- `rank`
- `reason`
- `scoring_version`
- `last_updated`

## 7. Scoring Design

Current scoring weights are defined in `backend/app/scoring/weights.py`.

| Signal | Weight |
| --- | --- |
| `absentee_owner` | 15 |
| `long_term_owner` | 10 |
| `tax_delinquent` | 25 |
| `pre_foreclosure` | 30 |
| `probate` | 20 |
| `code_violation` | 15 |

Current rank thresholds:

- Rank A: score >= 25
- Rank B: score >= 10 and < 25
- Rank C: score < 10

Current practical implication:

- a long-term-owner-only record now lands in Rank B rather than being grouped with zero-signal records
- the scoring framework is functioning, but richer distress-signal coverage is still the main remaining product-quality gap

## 8. Public API Surface

### 8.1 Health and Operational Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness check |
| `POST` | `/api/ingest/run` | Run live ingest |
| `GET` | `/api/cron/run-signals` | Protected full signal and scoring batch |

Admin auth accepted by ingest and cron routes:

- `Authorization: Bearer <CRON_SECRET>`
- `X-Cron-Secret: <CRON_SECRET>`
- `?cron_secret=<CRON_SECRET>` for manual debugging

### 8.2 Lead Read Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/leads` | Main leads list |
| `GET` | `/api/leads/top` | Alias of main leads list |
| `GET` | `/api/leads/new` | Recently updated leads |
| `GET` | `/api/leads/{parcel_id}` | Property detail by parcel ID |
| `GET` | `/api/property/{property_id}` | Property detail by UUID |

Lead list behavior:

- default `limit=50`
- max `limit=1000`
- optional `county` filter for `shelby` or `jefferson`
- response includes both `leads` and `total`

### 8.3 Export Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/leads/export` | CRM-ready export list |
| `GET` | `/api/leads/export/{property_id}` | CRM-ready single-property export |

## 9. Frontend Behavior

### 9.1 Dashboard

The dashboard uses the API `total` field for the headline property count and renders a top-five score view from the current lead slice across Shelby and Jefferson counties.

### 9.2 Leads Page

The leads page uses backend-driven filtering, sorting, and offset pagination. It exposes county as a first-class filter and passes county through property-detail navigation so duplicate parcel IDs across counties remain unambiguous.

### 9.3 Property Detail

Property detail is currently served from `/property?parcel_id=...&county=...` and retrieves data from `GET /api/leads/{parcel_id}` with an optional `county` query parameter.

## 10. Deployment Design

### 10.1 Vercel Routing

`vercel.json` currently routes:

- `/api/*` to `api/index.py`
- everything else to the Next app under `frontend/`

### 10.2 Python Serverless Entry

`api/index.py` adds `backend/` to `sys.path`, imports the FastAPI app, and exposes a Mangum handler.

### 10.3 Database Connectivity

Hosted deployments should use Supabase Postgres.

Important design constraint:

- Supabase pooled connections behave like PgBouncer transaction pooling
- asyncpg prepared-statement caching had to be disabled for pooled connections
- `backend/app/core/config.py` now detects pooled URLs and injects PgBouncer-safe asyncpg settings

County data sources currently wired:

- Shelby County parcels: public ArcGIS REST service already used by the repo
- Jefferson County parcels: public ArcGIS MapServer published by Jefferson County GIS at `https://jccgis.jccal.org/server/rest/services/Basemap/Parcels/MapServer/0`
- Shelby delinquency overlay: GovEase API endpoint used as a secondary signal source when available
- Jefferson delinquency overlay: not yet wired because a comparable public GovEase-style feed was not available during implementation research

### 10.4 Environment Model

The backend reads `.env` from the repository root.

Key variables:

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | runtime mode |
| `APP_HOST` / `APP_PORT` | backend bind settings |
| `DATABASE_URL` | async application DB URL |
| `DATABASE_SYNC_URL` | sync Alembic DB URL |
| `CORS_ALLOWED_ORIGINS` | local frontend origins |
| `API_URL` | server-side frontend API base fallback |
| `NEXT_PUBLIC_API_URL` | browser-facing API base override |
| `SCORING_VERSION` | score version tag |
| `SCORE_THRESHOLD` | threshold config |
| `WEBHOOK_URL` / `WEBHOOK_SECRET` | webhook integration |
| `WEBHOOK_SCORE_THRESHOLD` | webhook trigger threshold |
| `CRON_SECRET` | protection for ingest and cron admin flows |

## 11. Local Development

### 11.1 Prerequisites

- Python 3.11+ or compatible virtual environment
- Node.js 18+
- Docker

### 11.2 Local Database

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d db
```

Recommended local database values:

```env
DATABASE_URL=postgresql+asyncpg://rse_user:rse_password@localhost:5432/rse_db
DATABASE_SYNC_URL=postgresql://rse_user:rse_password@localhost:5432/rse_db
```

### 11.3 Backend

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
python main.py
```

Important: `alembic upgrade head` is a shell command run from your terminal in `backend/`. It is not SQL and will fail if you paste it into the Supabase SQL editor.

FastAPI docs will be available at `http://127.0.0.1:8000/docs`.

### 11.4 Frontend

```bash
cd frontend
npm install
npm run dev
```

### 11.5 Local Ingest Paths

Manual ingest through the API:

```bash
curl -X POST 'http://127.0.0.1:8000/api/ingest/run?dry_run=true&limit=100'
curl -X POST 'http://127.0.0.1:8000/api/ingest/run?limit=100' -H 'x-cron-secret: YOUR_SECRET'
curl -X POST 'http://127.0.0.1:8000/api/ingest/run?county=jefferson&dry_run=true&limit=100'
curl -X POST 'http://127.0.0.1:8000/api/ingest/run?county=all&limit=100' -H 'x-cron-secret: YOUR_SECRET'
```

CSV ingestion script for local and sample workflows:

```bash
cd backend
python scripts/ingest_properties.py --csv ../data/sample_properties.csv
```

### 11.6 Testing

```bash
cd backend
python -m pytest tests/ -q

cd ../frontend
npm run build
```

## 12. Operational Notes

- The ingest UI reports the number of fetched, upserted, signaled, and scored records for a run.
- The lead APIs return a default slice unless a larger `limit` is requested.
- Some county parcel records do not include a usable property street address; the API falls back to raw or mailing address fields for display.
- Jefferson County currently contributes parcel, owner, mailing, and assessed-value data, but not the same built-in deed-date or delinquency fields that Shelby exposes.
- Property detail navigation is currently query-based because that path is more stable in the deployed environment than parcel-based dynamic page routing.

## 13. Known Constraints

- The leads UI now pages through the backend result set, but it still uses offset pagination rather than a cursor model.
- Ranking quality is functional but not yet tuned for high-confidence business prioritization.
- The Vercel route setup is working, but it is sensitive because the repo hosts both the Next app and the Python API in one project.
- Distress signals such as probate, pre-foreclosure, and code violations exist in the schema and scoring model, but their live data sources are not yet fully implemented.
- Parcel IDs are only unique within a county, so downstream integrations must preserve both `county` and `parcel_id` when round-tripping records.

## 14. What’s Next

The next highest-value work items are:

1. Add a Jefferson-compatible distress overlay so Jefferson leads are not limited to parcel-only and ownership-only signals.
2. Improve scoring quality further by adding more distress-source data beyond the current absentee, long-term, and tax-overlay-heavy signal mix.
3. Move the leads API and UI from offset pagination to a cursor-based model if dataset size or latency starts to climb.
4. Harden deployment documentation and Vercel routing so property detail behavior is simpler and less fragile.
5. Add production monitoring for ingest duration, API failures, and cron execution outcomes.
