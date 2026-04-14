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
- signal generation for absentee ownership, long-term ownership, out-of-state owners, and likely corporate owners
- Shelby tax-delinquency ingestion path
- weighted lead scoring and rank assignment
- leads list, recent leads, property detail, CRM export, and cron APIs
- web dashboard, ingest UI, leads UI, and property detail UI
- Vercel deployment with FastAPI serverless API and Next.js frontend
- Vercel cron-compatible batch signal reruns using `CRON_SECRET`

Not fully realized yet:

- richer distress data sources beyond the current parcel and tax overlay set
- deeper ranking calibration for production-quality prioritization
- production monitoring and alerting for ingest/cron failures
- final UX polish for filtering, pagination, and operator workflows

## 3. Current Status

As of the current repository state, the project is in a usable MVP-plus state rather than an experimental prototype.

Working now:

- deployed FastAPI + Next.js application on Vercel
- Supabase-backed persistence with PgBouncer-safe async configuration
- county-aware parcel identity using `(county, parcel_id)`
- live Shelby + Jefferson parcel ingest
- Shelby tax-delinquency overlay ingest
- leads dashboard, lead feed, property detail, CRM export, and webhook payloads
- backend-driven lead filtering, sorting, and pagination
- daily Vercel cron wiring for signal/scoring refresh

Validated recently in this repo:

- backend tests passing after county, export, dashboard, and cron changes
- frontend production build passing
- production dashboard `422` contract mismatch fixed by reducing dashboard fetches to the shipped `/api/leads` cap
- advanced search Enter-to-apply behavior fixed on the leads page

Still intentionally incomplete:

- Jefferson-specific distress overlays beyond parcel ownership/value data
- production-grade observability, alerting, and job run dashboards
- richer ranking inputs for legal-distress and municipal-distress scenarios

## 4. System Overview

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

## 5. Architecture

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

## 6. Data Flow

### 6.1 Ingest Flow

1. `POST /api/ingest/run` triggers ArcGIS and optional overlay scrapers.
   Optional incremental parameters: `updated_since=<ISO timestamp>` or `delta_days=<N>`.
   Current source-side changed-since support is strongest for Shelby parcel data; unsupported sources fall back to a full fetch.
2. Results are merged by `parcel_id`.
3. Properties are upserted into the `properties` table.
4. Signal generation runs for the updated properties.
5. Tax-delinquency records are updated.
6. Scoring runs and writes rank and reason metadata.
7. The API returns a summary of fetched, upserted, signaled, and scored records.

### 6.2 Read Flow

1. Frontend pages call the FastAPI endpoints under `/api/*`.
2. Leads endpoints join `properties`, `signals`, and `scores`.
3. The API returns normalized response models.
4. The dashboard and lead feed render sorted slices of those results.

### 6.3 Scheduled Flow

`GET /api/cron/run-signals` is a protected endpoint that re-runs signal and scoring logic over existing properties.
The deployed Vercel cron calls this route daily using `CRON_SECRET` bearer authentication.

This same full scoring path is the one-time backfill mechanism for newly added scoring modes on existing properties.

The current schedule in `vercel.json` is `0 6 * * *` (06:00 UTC daily).

## 7. Core Data Model

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
- `out_of_state_owner`
- `corporate_owner`
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
- `scoring_mode`
- `scoring_version`
- `last_updated`

## 8. Scoring Design

Current scoring lenses are defined in `backend/app/scoring/weights.py`.

Signals remain universal property facts. Scores are now stored and read per scoring lens.

Current scoring modes:

- `broad` — blended opportunity ranking across seller and investor use cases; default mode for backward compatibility
- `owner_occupant` — prioritizes homeowner-style distress and long tenure while de-emphasizing investor ownership patterns
- `investor` — prioritizes absentee, out-of-state, and portfolio-style ownership alongside distress

Representative `broad` mode weights:

| Signal | Weight |
| --- | --- |
| `absentee_owner` | 15 |
| `long_term_owner` | 10 |
| `out_of_state_owner` | 12 |
| `corporate_owner` | 8 |
| `tax_delinquent` | 25 |
| `pre_foreclosure` | 30 |
| `probate` | 20 |
| `code_violation` | 15 |

### 8.1 Score Formula

The current score is:

`sum(active signal weights) + distress_combo_bonus`

Where:

- distress signals are `tax_delinquent`, `pre_foreclosure`, `probate`, and `code_violation`
- `distress_combo_bonus = 20`
- the bonus is added only when `2` or more distress signals are active

Rank thresholds are mode-specific. Current thresholds are:

- `broad`: A >= 25, B >= 10, C < 10
- `owner_occupant`: A >= 30, B >= 12, C < 12
- `investor`: A >= 28, B >= 12, C < 12

### 8.2 Implemented vs Placeholder Signals

The schema and scoring model support more signals than the live ingest currently powers.

Implemented with real data today:

- `absentee_owner`
   source: property vs mailing address comparison
   implementation: computed in `SignalEngine`
- `long_term_owner`
   source: `last_sale_date`
   implementation: computed in `SignalEngine`
- `out_of_state_owner`
   source: state suffix inferred from normalized mailing address versus property state
   implementation: computed in `SignalEngine`
- `corporate_owner`
   source: owner-name entity matching for LLC, trust, holdings, and similar patterns
   implementation: computed in `SignalEngine`
- `tax_delinquent`
   source: Shelby overlay / explicit tax-delinquency ingestion
   implementation: written through `TaxDelinquencyService`

Present in the model but still placeholder-stubbed in the signal engine:

- `pre_foreclosure`
- `probate`
- `eviction`
- `code_violation`

This matters because the scoring model is broader than the live input coverage. Rank math is already in place for distress-heavy cases, but most current production records are still driven by ownership and tax-overlay signals rather than a full distress stack.

### 8.3 Practical Scoring Examples

Examples below use the default `broad` mode unless noted otherwise.

| Active signals | Score | Rank |
| --- | --- | --- |
| none | 0 | C |
| `corporate_owner` | 8 | C |
| `long_term_owner` | 10 | B |
| `out_of_state_owner` | 12 | B |
| `absentee_owner` | 15 | B |
| `absentee_owner` + `long_term_owner` | 25 | A |
| `tax_delinquent` | 25 | A |
| `probate` | 20 | B |
| `tax_delinquent` + `pre_foreclosure` | 75 | A |

The last example is `25 + 30 + 20 distress bonus = 75`.

### 8.4 Current Scoring Limitations

- the new owner-pattern signals are intentionally heuristic rather than title-perfect; they broaden lead coverage across both counties but still need production tuning against actual deal outcomes
- Jefferson data currently contributes parcel, address, mailing, ownership, and value data, but not the richer distress overlays needed to fully exploit the higher-value scoring branches.
- `pre_foreclosure`, `probate`, `eviction`, and `code_violation` are scored if present, but their live ingestion pipelines are not yet implemented.
- `tax_delinquent` is materially stronger in Shelby than Jefferson because the Shelby overlay path is real and Jefferson currently lacks an equivalent public source in this repo.

### 8.5 Scoring Expansion Plan

Highest-value next improvements:

1. Add a Jefferson-compatible tax or legal-distress overlay.
2. Add probate ingestion so inherited/distressed ownership changes become first-class signals.
3. Add pre-foreclosure or court-derived legal-distress inputs.
4. Add code-violation / nuisance-property data where public sources exist.
5. Recalibrate weights only after the new inputs exist, so thresholds are tuned on real signal coverage rather than placeholder math.

Current practical implication:

- a long-term-owner-only record now lands in Rank B rather than being grouped with zero-signal records
- the scoring framework is functioning, but richer distress-signal coverage is still the main remaining product-quality gap

## 9. Public API Surface

### 9.1 Health and Operational Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness check |
| `POST` | `/api/ingest/run` | Run live ingest |
| `GET` | `/api/cron/run-signals` | Protected full signal and scoring batch |

Admin auth accepted by ingest and cron routes:

- `Authorization: Bearer <CRON_SECRET>`
- `X-Cron-Secret: <CRON_SECRET>`
- `?cron_secret=<CRON_SECRET>` for manual debugging

### 9.2 Lead Read Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/leads` | Main leads list |
| `GET` | `/api/leads/top` | Alias of main leads list |
| `GET` | `/api/leads/new` | Recently updated leads |
| `GET` | `/api/leads/{parcel_id}` | Property detail by parcel ID |
| `GET` | `/api/property/{property_id}` | Property detail by UUID |

Lead list behavior:

- default `limit=50`
- max `limit=250`
- optional `county` filter for `shelby` or `jefferson`
- optional `scoring_mode` filter for `broad`, `owner_occupant`, or `investor`
- response includes both `leads` and `total`

`GET /api/leads/new` remains a separate recent-leads path with a higher cap.

### 9.3 Export Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/leads/export` | CRM-ready export list |
| `GET` | `/api/leads/export/{property_id}` | CRM-ready single-property export |

Export payloads now include `property.county` so downstream systems can safely distinguish duplicate parcel IDs across counties.

## 10. Frontend Behavior

### 10.1 Dashboard

The dashboard uses the API `total` field for the headline property count and renders a top-five score view from the current lead slice across Shelby and Jefferson counties.

The dashboard, leads page, and property detail now preserve a selected scoring lens through the `scoring_mode` query parameter.

### 10.2 Leads Page

The leads page uses backend-driven filtering, sorting, and offset pagination. It exposes county as a first-class filter and passes county through property-detail navigation so duplicate parcel IDs across counties remain unambiguous.

The advanced search panel now supports submitting filters by pressing Enter, not just by clicking Apply.

### 10.3 Property Detail

Property detail is currently served from `/property?parcel_id=...&county=...` and retrieves data from `GET /api/leads/{parcel_id}` with an optional `county` query parameter.

## 11. Deployment Design

### 11.1 Vercel Routing

`vercel.json` currently routes:

- `/api/*` to `api/index.py`
- everything else to the Next app under `frontend/`

Vercel cron is also configured here to call `/api/cron/run-signals` daily.

### 11.2 Python Serverless Entry

`api/index.py` adds `backend/` to `sys.path`, imports the FastAPI app, and exposes a Mangum handler.

### 11.3 Database Connectivity

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

### 11.4 Environment Model

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

Hosted runtime notes:

- `DATABASE_URL` should be the async application URL used by the FastAPI runtime
- `DATABASE_SYNC_URL` should be the sync URL used for Alembic and other sync tooling
- production Supabase pooled connections are expected and explicitly handled by the config layer

## 12. Local Development

### 12.1 Prerequisites

- Python 3.11+ or compatible virtual environment
- Node.js 18+
- Docker

### 12.2 Local Database

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d db
```

Recommended local database values:

```env
DATABASE_URL=postgresql+asyncpg://rse_user:rse_password@localhost:5432/rse_db
DATABASE_SYNC_URL=postgresql://rse_user:rse_password@localhost:5432/rse_db
```

### 12.3 Backend

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
python main.py
```

Important: `alembic upgrade head` is a shell command run from your terminal in `backend/`. It is not SQL and will fail if you paste it into the Supabase SQL editor.

If you need to apply revision `0003` manually in the Supabase SQL editor, paste this SQL instead of the Alembic Python migration file:

```sql
alter table public.signals
add column if not exists out_of_state_owner boolean not null default false;

alter table public.signals
add column if not exists corporate_owner boolean not null default false;

update public.alembic_version
set version_num = '0003'
where version_num = '0002';
```

That manual SQL is equivalent to the migration in `backend/alembic/versions/0003_add_cross_county_signals.py` plus the version-table update Alembic would normally manage for you.

If you need to apply revision `0004` manually in the Supabase SQL editor, paste this SQL instead of the Alembic Python migration file:

```sql
alter table public.scores
add column if not exists scoring_mode varchar(32) not null default 'broad';

update public.scores
set scoring_mode = 'broad'
where scoring_mode is null;

alter table public.scores
drop constraint if exists uq_scores_property_id;

alter table public.scores
add constraint uq_scores_property_mode unique (property_id, scoring_mode);

create index if not exists ix_scores_scoring_mode on public.scores (scoring_mode);

update public.alembic_version
set version_num = '0004'
where version_num = '0003';
```

That manual SQL is equivalent to the migration in `backend/alembic/versions/0004_add_scoring_mode_to_scores.py` plus the version-table update Alembic would normally manage for you.

FastAPI docs will be available at `http://127.0.0.1:8000/docs`.

### 12.4 Frontend

```bash
cd frontend
npm install
npm run dev
```

### 12.5 Local Ingest Paths

Manual ingest through the API:

```bash
curl -X POST 'http://127.0.0.1:8000/api/ingest/run?dry_run=true&limit=100'
curl -X POST 'http://127.0.0.1:8000/api/ingest/run?limit=100' -H 'x-cron-secret: YOUR_SECRET'
curl -X POST 'http://127.0.0.1:8000/api/ingest/run?county=jefferson&dry_run=true&limit=100'
curl -X POST 'http://127.0.0.1:8000/api/ingest/run?county=all&limit=100' -H 'x-cron-secret: YOUR_SECRET'
curl -X POST 'http://127.0.0.1:8000/api/ingest/run?county=shelby&delta_days=1&dry_run=true'
curl -X POST 'http://127.0.0.1:8000/api/ingest/run?county=shelby&updated_since=2026-04-13T00:00:00Z' -H 'x-cron-secret: YOUR_SECRET'
```

Equivalent bearer-auth pattern:

```bash
curl -X POST 'http://127.0.0.1:8000/api/ingest/run?county=all&limit=100' \
   -H 'Authorization: Bearer YOUR_SECRET'
```

CSV ingestion script for local and sample workflows:

```bash
cd backend
python scripts/ingest_properties.py --csv ../data/sample_properties.csv
```

Scoring-only backfill for existing properties:

```bash
cd backend
python scripts/run_scoring.py
```

### 12.6 Testing

```bash
cd backend
python -m pytest tests/ -q

cd ../frontend
npm run build
```

## 13. Operational Notes

- The ingest UI reports the number of fetched, upserted, signaled, and scored records for a run.
- The main lead API caps results at `250` per request; dashboard and leads UI are aligned to that cap.
- Some county parcel records do not include a usable property street address; the API falls back to raw or mailing address fields for display.
- Jefferson County currently contributes parcel, owner, mailing, and assessed-value data, but not the same built-in deed-date or delinquency fields that Shelby exposes.
- Property detail navigation is currently query-based because that path is more stable in the deployed environment than parcel-based dynamic page routing.
- Cron auth now supports bearer-token flows that are compatible with Vercel scheduler behavior.

## 14. Known Constraints

- The leads UI now pages through the backend result set, but it still uses offset pagination rather than a cursor model.
- Ranking quality is functional but not yet tuned for high-confidence business prioritization.
- The Vercel route setup is working, but it is sensitive because the repo hosts both the Next app and the Python API in one project.
- Distress signals such as probate, pre-foreclosure, and code violations exist in the schema and scoring model, but their live data sources are not yet fully implemented.
- Parcel IDs are only unique within a county, so downstream integrations must preserve both `county` and `parcel_id` when round-tripping records.

Operationally, the biggest remaining quality gap is not the score formula itself but the lack of more live distress inputs feeding that formula.

## 15. Forward Plan

The next highest-value work items are:

1. Add Jefferson-compatible distress overlays so Jefferson ranking is not limited mostly to parcel and ownership signals.
2. Implement probate, pre-foreclosure, and code-violation ingestion before doing another major scoring recalibration.
3. Add production monitoring for ingest duration, cron execution results, and API failures.
4. Consider cursor pagination if lead volume or response time grows past what offset pagination handles comfortably.
5. Continue tightening docs, operator runbooks, and deployment visibility as the product moves from MVP toward production operations.
