# Real Estate Signal Engine

Real Estate Signal Engine (RSE) is a lead generation system for public real estate data. It ingests county parcel records and tax-delinquency overlays, derives seller-investor signals, scores each parcel across three configurable scoring lenses, and exposes the results through a FastAPI backend and a mobile-responsive Next.js dashboard.

## 1. Purpose

The system is designed to answer one question:

Which properties in the covered Alabama counties look most likely to represent actionable seller or investor opportunities?

The current focus:

- ingesting parcel data from Shelby County ArcGIS and Jefferson County ArcGIS
- overlaying delinquency signals from the Shelby GovEase feed
- computing repeatable signal flags and a weighted lead score
- scoring properties across three lens modes: Broad, Owner Occupant, and Investor
- surfacing ranked leads in a mobile-responsive browser UI and JSON APIs

## 2. Current Coverage

As of the latest ingest, the database holds approximately 66,000+ properties across Shelby and Jefferson counties with signals and scores computed for all three modes.

Signals fully implemented with live data:

- `absentee_owner` — property vs mailing address mismatch
- `long_term_owner` — no recorded sale in 10+ years
- `out_of_state_owner` — mailing address outside Alabama
- `corporate_owner` — owner name matches LLC, trust, or holdings patterns
- `tax_delinquent` — Shelby overlay via GovEase

Signals present in the schema and scoring model but not yet backed by live ingestion:

- `pre_foreclosure`, `probate`, `eviction`, `code_violation`

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
      +--> SignalEngine (per-property savepoints + deadlock retry)
      |         |
      |         v
      |     signals table
      |
      +--> TaxDelinquencyService (savepoints + deadlock retry)
      |
      +--> ScoringEngine (per-mode, per-property savepoints + deadlock retry)
      |         |
      |         v
      |     scores table  (one row per property × scoring mode)
      |
      v
   FastAPI read APIs
      |
      v
   Next.js dashboard, lead feed, property detail
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
| Leads API | `backend/app/api/leads.py` | Lead list, sorting, filtering, pagination, property detail |
| Health API | `backend/app/api/health.py` | Liveness and DB stats |
| Export API | `backend/app/api/export.py` | CRM export endpoints |
| Cron API | `backend/app/api/cron.py` | Protected batch signal + scoring rescore endpoint |
| Scrapers | `backend/app/scrapers/` | ArcGIS and GovEase ingestion logic |
| Signals | `backend/app/signals/engine.py` | Signal generation with per-property savepoints and deadlock retry |
| Scoring | `backend/app/scoring/engine.py` | Score and rank generation, all modes, savepoints and deadlock retry |
| Tax svc | `backend/app/services/tax_delinquency.py` | Tax-delinquency upsert with savepoints and deadlock retry |

### 4.4 Main Frontend Routes

| Route | Purpose |
| --- | --- |
| `/` | Dashboard — headline stats, top-5 leads by score, scoring lens selector |
| `/ingest` | Ingest runner, rescore tool, live DB status |
| `/leads` | Searchable, sortable, paginated lead feed with collapsible advanced search |
| `/property?parcel_id=...` | Property detail — signals, score drivers, Maps link, GIS source link |
| `/lists` | Property lists — create/delete named lists, add/remove properties, export CSV |
| `/map` | Map view — properties as color-coded pins on OpenStreetMap, saveable views |
| `/auth` | Sign In / Create Account (email + password via Supabase) |

## 5. Data Flow

### 5.1 Ingest Flow

1. `POST /api/ingest/run` triggers ArcGIS and optional overlay scrapers.
   Optional incremental parameters: `updated_since=<ISO timestamp>` or `delta_days=<N>`.
2. Results are merged by `parcel_id`.
3. Properties are upserted into the `properties` table (keyed by `(county, parcel_id)`).
4. Signal generation runs per property using savepoints — a failure on one property rolls back only that savepoint, not the whole batch.
5. Tax-delinquency records are updated via `TaxDelinquencyService`.
6. Scoring runs across all three modes and writes rank and reason metadata.
7. Transient deadlocks are retried up to 3× with exponential backoff at each layer.
8. The API returns a summary of fetched, upserted, signaled, and scored records. On failure, `signals.error` and `scoring.error` fields are populated in the response (never silently masked as success counts).

Large-scale ingests use auto-batching from the UI: a full single-county ingest is broken into 250-record chunks client-side, with cumulative stats displayed in real time.

### 5.2 Read Flow

1. Frontend pages call FastAPI endpoints under `/api/*`.
2. Lead endpoints join `properties`, `signals`, and `scores`.
3. Results are sorted, filtered, and paginated server-side.
4. The dashboard and lead feed render sorted slices. All pages preserve the selected scoring lens via `?scoring_mode=` query parameter.

### 5.3 Scheduled Flow

`GET /api/cron/run-signals` is a protected endpoint that re-runs signal and scoring logic over all existing properties in offset-paginated batches of 500.

The deployed Vercel cron calls this route daily at `0 6 * * *` (06:00 UTC).

The same endpoint is also used for on-demand full rescores from the ingest UI.

## 6. Core Data Model

### 6.1 `properties`

Canonical parcel record keyed by `(county, parcel_id)`.

Key fields: `county`, `parcel_id`, `address`, `city`, `state`, `zip`, `owner_name`, `mailing_address`, `last_sale_date`, `assessed_value`, `lat`, `lng`

`lat` and `lng` are WGS84 coordinates extracted from the ArcGIS polygon centroid at ingest time. Null for properties where ArcGIS returned no geometry.

### 6.2 `signals`

Boolean flags derived from property and owner characteristics. One row per property.

Current fields: `absentee_owner`, `long_term_owner`, `out_of_state_owner`, `corporate_owner`, `tax_delinquent`, `pre_foreclosure`, `probate`, `eviction`, `code_violation`

### 6.3 `scores`

Weighted output of the scoring pipeline. One row per `(property_id, scoring_mode)`.

Key fields: `score`, `rank`, `reason` (list of contributing signal keys), `scoring_mode`, `scoring_version`, `last_updated`

### 6.4 `saved_searches` (user data)

Named filter snapshots owned by a Supabase Auth user. One row per search.

Key fields: `id`, `user_id`, `name`, `filters` (JSONB — stores all active lead-feed query parameters), `created_at`

Protected by RLS: users can only read and write their own rows.

### 6.5 `property_lists` (user data)

Named property collections owned by a Supabase Auth user.

Key fields: `id`, `user_id`, `name`, `created_at`

Protected by RLS: users can only read and write their own rows.

### 6.6 `property_list_items` (user data)

Join table between a property list and a parcel. Stores the `county` + `parcel_id` pair so the list remains valid even if the `properties` UUID changes.

Key fields: `id`, `list_id`, `county`, `parcel_id`, `added_at`

Protected by RLS: users can only access items belonging to lists they own.

## 7. Scoring Design

Signals are universal property facts. Scores are computed per lens and stored separately so switching lenses does not require re-running signal detection.

### 7.1 Scoring Modes

| Mode | Key | Description |
| --- | --- | --- |
| Broad | `broad` | Blended opportunity ranking across seller and investor use cases. Default. |
| Owner Occupant | `owner_occupant` | Prioritizes homeowner-style distress and long tenure; de-emphasizes investor ownership patterns. |
| Investor | `investor` | Prioritizes absentee, out-of-state, and portfolio-style ownership alongside distress. |

### 7.2 Score Formula

```text
score = sum(active signal weights) + distress_combo_bonus
```

Where:

- distress signals are `tax_delinquent`, `pre_foreclosure`, `probate`, `code_violation`
- `distress_combo_bonus = 20` when 2+ distress signals are active

### 7.3 `broad` Mode Weights

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

### 7.4 Rank Thresholds

| Mode | A | B | C |
| --- | --- | --- | --- |
| `broad` | ≥ 25 | ≥ 10 | < 10 |
| `owner_occupant` | ≥ 30 | ≥ 12 | < 12 |
| `investor` | ≥ 28 | ≥ 12 | < 12 |

### 7.5 Scoring Examples (`broad`)

| Active signals | Score | Rank |
| --- | --- | --- |
| none | 0 | C |
| `long_term_owner` | 10 | B |
| `absentee_owner` + `long_term_owner` | 25 | A |
| `tax_delinquent` | 25 | A |
| `tax_delinquent` + `pre_foreclosure` | 75 | A |

The last example: `25 + 30 + 20 distress combo bonus = 75`.

### 7.6 Current Scoring Limitations

- `pre_foreclosure`, `probate`, `eviction`, and `code_violation` are scored if present but their live ingestion pipelines are not yet implemented.
- `tax_delinquent` is materially stronger for Shelby than Jefferson because the Shelby GovEase overlay is active; Jefferson lacks an equivalent public source in this repo.
- Jefferson contributes parcel, address, mailing, ownership, and assessed-value data but not the richer distress overlays that fully exploit the higher-weight scoring branches.

## 8. Frontend Features

### 8.1 Dashboard (`/`)

- Headline stat cards: Total Properties, Signals Detected, Top Leads (Rank A)
- Scoring lens selector persists across all pages via `?scoring_mode=` query parameter
- Top-5 leads by score with click-through to property detail
- Auto-refreshes every 60 seconds; manual refresh button

### 8.2 Lead Feed (`/leads`)

- Backend-driven filtering, sorting, and offset pagination
- **Collapsible advanced search** (closed by default) — filter by county, city, owner, parcel ID, score range, assessed value range
- **Rank filter** — A/B/C buttons apply immediately without requiring Apply
- **Sortable columns** — all columns including Rank (defaults ascending, A-leads first) and Owner
- **Mobile sort bar** — scrollable pill row for Score, Rank, Value, Owner, Updated
- **Mobile card view** — tap-friendly cards with score, rank, signals, value, and date; desktop gets full table
- Scoring lens selector with per-lens result counts
- Pagination with page size up to 250 records per page

### 8.3 Property Detail (`/property?parcel_id=...&county=...`)

- Full property info card: owner, county, parcel ID, score, rank, signals detected, scoring mode, scoring version, mailing address, assessed value, last updated
- **Active Signals** section — signal badges with hover tooltips explaining what each signal means
- **Score Drivers** section — driver badges explaining why each signal contributes to the score, with distress combo bonus highlighted separately in amber
- **Open in Maps** link — opens Google Maps for the property address
- **Source Data** section — direct link to the relevant county GIS portal (Shelby or Jefferson)
- Scoring lens awareness: detail is fetched for the active lens

### 8.4 Ingest Page (`/ingest`)

- **Options**: dry run, delinquent-only mode, county scope, record limit, cron secret
- **Auto-batch mode**: full single-county ingest automatically batches in 250-record chunks with real-time cumulative progress
- **Run button**: animated spinner during active ingest; stays blue rather than going gray
- **Progress display**: in-progress card with pulsing indicator and batch status
- **Result summary**: fetched / upserted / signals / scored stat tiles; error fields shown if any layer failed
- **Rescore tool**: triggers the full signal + scoring pipeline over all existing properties via the cron endpoint; inline spinner and progress tracker
- **DB Status bar**: live counts for properties, signals, and per-mode scores with a refresh button

### 8.5 Map View (`/map`)

Properties are displayed as color-coded pins on an OpenStreetMap base layer using Leaflet. Coordinates are extracted from ArcGIS polygon geometry at ingest time and stored as `lat`/`lng` on the `properties` table — no geocoding API required.

- **Rank-coded pins**: green (A), yellow (B), gray (C)
- **Filter bar**: scoring lens, county, rank, and keyword search — same parameters as the lead feed
- **Property panel**: click any pin to open a side panel with address, owner, score, rank, value, View Detail link, Maps link, and Add to List dropdown
- **Save View**: authenticated users can save the current filter state (including map viewport) as a named saved search, reloadable from the lead feed's saved searches menu
- **List/Map toggle**: link in the header to switch between feed and map views
- Properties without coordinates (ArcGIS returned no geometry) are excluded from the map; the filter bar shows counts for mapped vs. total results

### 8.6 User Accounts (`/auth`, `/lists`)

User accounts are powered by Supabase Auth (email + password). The Supabase browser client handles all user-data CRUD directly from the browser using Row Level Security — no user data flows through the FastAPI backend.

**Authentication:**

- Sign In / Create Account page at `/auth`
- `AuthProvider` React context wraps the app and exposes `user`, `signIn`, `signUp`, `signOut`
- Session persists across page refreshes via Supabase's built-in local storage

**Saved Searches:**

- Save any active filter combination under a user-chosen name from the lead feed header
- Load a saved search to restore all filters instantly
- Export a saved search to CSV (calls the FastAPI leads API with saved filters)
- All saved searches are private to the authenticated user

**Property Lists:**

- Create named lists and add properties from the property detail page via the "Add to List" button
- The button shows a checkmark dropdown listing all lists; click to toggle membership
- View all lists at `/lists`: expand a list to see all properties with address, owner, score, and rank
- Remove individual properties from a list or delete the entire list
- Export any list to CSV including joined property data

### 8.7 Mobile Layout

- Fixed top bar on mobile with app title and sign-in / sign-out control
- Bottom tab navigation (Dashboard / Leads / Lists / Ingest)
- Desktop gets a persistent left sidebar with user email and sign-out link
- All pages use responsive padding and stacked layouts on small screens

## 9. Backend Reliability

### 9.1 Per-Property Savepoints

Signal generation, scoring, and tax-delinquency writes all use `session.begin_nested()` savepoints per property. A SQL failure on one property rolls back only that savepoint — the outer transaction continues and the remaining properties in the batch are unaffected.

This replaces the previous pattern where a single property failure would abort the entire batch transaction with `InFailedSQLTransactionError`.

### 9.2 Deadlock Retry

Each per-property write block retries up to 3 times with exponential backoff (50 ms, 100 ms) on `DeadlockDetectedError`. This handles transient lock contention between concurrent ingest and cron runs without surfacing errors to the operator.

### 9.3 Honest Error Reporting

The ingest API resets `score_result` and `signal_result` in the exception handler so that a failed commit never reports success counts. The `signals.error` and `scoring.error` fields in the ingest response surface the actual error text when a layer fails.

The cron endpoint returns a JSON error body instead of a bare HTTP 500 so failures are readable in the rescore UI.

## 10. Public API Surface

### 10.1 Health and Operational Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness check |
| `GET` | `/api/health/stats` | DB record counts: properties, signals, per-mode scores |
| `POST` | `/api/ingest/run` | Run live ingest |
| `GET` | `/api/cron/run-signals` | Protected full signal and scoring rescore batch |

Auth accepted by ingest and cron routes:

- `Authorization: Bearer <CRON_SECRET>`
- `X-Cron-Secret: <CRON_SECRET>`
- `?cron_secret=<CRON_SECRET>` for manual debugging

### 10.2 Lead Read Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/leads` | Main leads list |
| `GET` | `/api/leads/top` | Alias of main leads list |
| `GET` | `/api/leads/new` | Recently updated leads |
| `GET` | `/api/leads/{parcel_id}` | Property detail by parcel ID |
| `GET` | `/api/property/{property_id}` | Property detail by UUID |

Lead list parameters:

| Parameter | Type | Description |
| --- | --- | --- |
| `limit` | int | Max records (default 50, max 250) |
| `offset` | int | Pagination offset |
| `county` | string | `shelby` or `jefferson` |
| `scoring_mode` | string | `broad`, `owner_occupant`, `investor` |
| `sort_by` | string | `score`, `rank`, `assessed_value`, `address`, `city`, `county`, `owner_name`, `last_updated` |
| `sort_dir` | string | `asc` or `desc` |
| `rank` | string | `A`, `B`, or `C` |
| `search` | string | Substring match across address, owner, parcel ID |
| `owner` | string | Owner name substring |
| `city` | string | City substring |
| `parcel_id` | string | Parcel ID substring |
| `min_score` / `max_score` | float | Score range |
| `min_value` / `max_value` | float | Assessed value range |

### 10.3 Export Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/leads/export` | CRM-ready export list |
| `GET` | `/api/leads/export/{property_id}` | CRM-ready single-property export |

Export payloads include `property.county` so downstream systems can safely distinguish duplicate parcel IDs across counties.

## 11. Deployment

### 11.1 Vercel Routing

`vercel.json` routes:

- `/api/*` → `api/index.py` (Python/FastAPI)
- everything else → Next.js frontend under `frontend/`

Vercel cron is configured to call `GET /api/cron/run-signals` daily at 06:00 UTC.

### 11.2 Python Serverless Entry

`api/index.py` adds `backend/` to `sys.path`, imports the FastAPI app, and exposes a Mangum handler.

### 11.3 Database Connectivity

Hosted deployments use Supabase PostgreSQL.

Important: Supabase pooled connections behave like PgBouncer transaction pooling. asyncpg prepared-statement caching is disabled for pooled connections. `backend/app/core/config.py` detects pooled URLs and injects PgBouncer-safe asyncpg settings automatically.

### 11.4 Environment Variables

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | Runtime mode |
| `DATABASE_URL` | Async application DB URL (asyncpg) |
| `DATABASE_SYNC_URL` | Sync Alembic DB URL |
| `CORS_ALLOWED_ORIGINS` | Local frontend origins |
| `API_URL` | Server-side frontend API base fallback |
| `NEXT_PUBLIC_API_URL` | Browser-facing API base override |
| `SCORING_VERSION` | Score version tag |
| `CRON_SECRET` | Auth for ingest and cron admin flows |
| `SUPABASE_URL` | Supabase project URL (backend) |
| `SUPABASE_ANON_KEY` | Supabase anon key (backend) |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL (browser) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key (browser) |
| `WEBHOOK_URL` / `WEBHOOK_SECRET` | Webhook integration |
| `WEBHOOK_SCORE_THRESHOLD` | Webhook trigger threshold |

## 12. Local Development

### 12.1 Prerequisites

- Python 3.11+
- Node.js 18+
- Docker

### 12.2 Local Database

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d db
```

Recommended local `.env` values:

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

FastAPI docs: `http://127.0.0.1:8000/docs`

> Note: `alembic upgrade head` is a terminal command, not SQL. Do not paste it into the Supabase SQL editor.

### 12.4 Frontend

```bash
cd frontend
npm install
npm run dev
```

### 12.5 Ingest Commands

```bash
# Dry run (no writes)
curl -X POST 'http://127.0.0.1:8000/api/ingest/run?dry_run=true&limit=100'

# Live ingest with limit
curl -X POST 'http://127.0.0.1:8000/api/ingest/run?limit=100' -H 'x-cron-secret: YOUR_SECRET'

# Jefferson dry run
curl -X POST 'http://127.0.0.1:8000/api/ingest/run?county=jefferson&dry_run=true&limit=100'

# Incremental ingest (last day)
curl -X POST 'http://127.0.0.1:8000/api/ingest/run?county=shelby&delta_days=1&dry_run=true'

# Full rescore batch (offset-paginated)
curl 'http://127.0.0.1:8000/api/cron/run-signals?offset=0&limit=500' -H 'x-cron-secret: YOUR_SECRET'
```

### 12.6 Testing

```bash
cd backend
python -m pytest tests/ -q

cd ../frontend
npm run build
```

## 13. Operational Notes

- All three scoring modes (Broad, Owner Occupant, Investor) must be populated before the lens selector shows meaningful data. Use the Rescore tool on the ingest page after a fresh ingest to populate all modes.
- The ingest UI auto-batches a full county ingest into 250-record chunks. Leave the record limit blank with a single county selected for this mode.
- The cron endpoint processes 500 properties per request. A full rescore of 66,000 properties takes approximately 133 requests and is driven from the ingest page.
- The lead API caps at 250 records per request. The dashboard and lead feed are aligned to this cap.
- Some parcel records lack a usable street address. The API falls back to raw or mailing address fields for display.
- Parcel IDs are only unique within a county. All downstream integrations must preserve both `county` and `parcel_id`.
- Jefferson contributes parcel, owner, mailing, and assessed-value data but not the same built-in deed-date or delinquency fields that Shelby exposes.

## 14. Known Constraints

- The leads feed uses offset pagination. If lead volume grows significantly, cursor pagination may be needed.
- `pre_foreclosure`, `probate`, `eviction`, and `code_violation` exist in the schema and scoring model but live data sources are not yet implemented.
- Jefferson tax and legal-distress overlays are not yet wired. Jefferson ranking is currently driven by ownership and value signals rather than a full distress stack.
- Ranking quality is functional but not yet tuned against real deal outcome data.

## 15. Forward Plan

Highest-value next improvements:

1. Add a Jefferson-compatible tax or legal-distress overlay so Jefferson ranking is not limited to parcel and ownership signals.
2. Implement probate ingestion so inherited/distressed ownership becomes a first-class signal.
3. Add pre-foreclosure or court-derived legal-distress data.
4. Add code-violation / nuisance-property data where public sources exist.
5. Recalibrate score weights only after the new inputs exist — so thresholds are tuned against real signal coverage rather than placeholder math.
6. Add production monitoring for ingest duration, cron execution results, and API error rates.
7. Consider cursor pagination if lead volume or response time grows past what offset pagination handles comfortably.
