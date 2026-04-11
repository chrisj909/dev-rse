# Real Estate Signal Engine (RSE)

Transforms public real estate, court, and municipal data into ranked, high-probability seller/investor opportunities.

**Target market:** Shelby County, Alabama (MVP)

---

## Architecture

```text
[Scrapers] → [Raw Data Store] → [Normalizer] → [Signal Engine] → [Scoring Engine] → [API] → [Dashboard]
```

## Stack

| Layer | Tech |
| --- | --- |
| Backend API | Python 3.11, FastAPI |
| Database | PostgreSQL (Neon / Supabase on Vercel; Docker Compose locally) |
| ORM / Migrations | SQLAlchemy 2 (async) + Alembic |
| Serverless adapter | Mangum (ASGI → Lambda / Vercel) |
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Deployment | Vercel |

---

## Project Structure

```text
rse/
├── api/              ← Vercel Python serverless entry point (wraps FastAPI)
├── backend/          ← FastAPI application
│   ├── app/
│   │   ├── api/      ← Route handlers
│   │   ├── core/     ← Config, settings
│   │   ├── db/       ← Session management
│   │   ├── models/   ← SQLAlchemy ORM models
│   │   ├── services/ ← Address normalization, signal detectors
│   │   ├── signals/  ← SignalEngine (Sprint 3)
│   │   └── scoring/  ← ScoringEngine (Sprint 3)
│   ├── alembic/      ← Database migrations
│   ├── scripts/      ← CLI jobs (ingest, batch signal run)
│   └── tests/        ← pytest test suite
├── data/             ← Sample CSV seed data
├── frontend/         ← Next.js 14 dashboard
├── infra/            ← Docker Compose for local development
├── vercel.json       ← Vercel deployment config
└── .env.example      ← Environment variable template
```

---

## Local Development

### Prerequisites

- Docker + Docker Compose
- Python 3.11+
- Node.js 18+

### Database Modes

- Local QA/dev: use the Docker Postgres service in [infra/docker-compose.yml](/workspaces/dev-rse/infra/docker-compose.yml)
- Vercel/production: use Supabase via `DATABASE_URL` and `DATABASE_SYNC_URL`
- Do not point ad hoc test ingests at production Supabase unless you want test rows there

### Start the backend

```bash
# From rse/
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d db

cd backend
pip install -r requirements.txt
alembic upgrade head
python main.py
```

API available at `http://localhost:8000`
Docs at `http://localhost:8000/docs`

Notes:

- The backend reads `.env` from the repo root, not `backend/.env`
- For Codespaces/local frontend access, set `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`
- If you want to test against Supabase instead of local Docker, replace `DATABASE_URL` and `DATABASE_SYNC_URL` in `.env` before running migrations or ingest

### Run data ingestion

```bash
cd backend
python scripts/ingest_properties.py --csv ../data/sample_properties.csv
```

### Run signal batch job (Sprint 3)

```bash
cd backend
python scripts/run_signals.py
```

### Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard at `http://localhost:3000`

### Run tests

```bash
cd backend
python -m pytest tests/ -v
```

---

## Deployment (Vercel)

1. Connect this repo to Vercel
2. Set environment variables on Vercel:
   - `DATABASE_URL` — Supabase Postgres async connection string
   - `DATABASE_SYNC_URL` — matching sync Postgres connection string for migrations
   - `APP_ENV` — `production`
   - `SCORING_VERSION` — `v1`
   - `CRON_SECRET` — required for `/api/cron/run-signals`
   - `NEXT_PUBLIC_API_URL` — set to your Vercel project URL if the frontend must call the deployed API explicitly
3. Deploy — Vercel routes `/api/*` to the Python function and `/*` to Next.js

### Verified API Paths

- `GET /api/health`
- `GET /api/leads`
- `GET /api/leads/top`
- `GET /api/leads/new`
- `GET /api/leads/{parcel_id}`
- `POST /api/ingest/run`
- `GET /api/cron/run-signals`

### Recommended Release Flow

1. Verify frontend build and `npm audit` are clean
2. Verify backend tests pass
3. Point `.env` at local Docker Postgres for a safe ingest smoke test
4. After ingest behavior is validated, switch Vercel env vars to Supabase and redeploy
5. Run a very small ingest against Supabase first, then confirm leads appear in the deployed UI

---

## Build Progress

| Sprint | Tasks | Status |
| --- | --- | --- |
| Sprint 1 | FastAPI + DB schema + address normalizer | ✅ Complete |
| Sprint 2 | CSV ingestion + absentee/long-term signals | ✅ Complete |
| Sprint 3 | SignalEngine + batch job + ScoringEngine | 🔄 In Progress |
| Sprint 4 | Lead API endpoints + unit tests | ⬜ Pending |
| Sprint 5 | Extensibility hooks + webhooks | ⬜ Pending |
