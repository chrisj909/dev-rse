# Real Estate Signal Engine (RSE)

Transforms public real estate, court, and municipal data into ranked, high-probability seller/investor opportunities.

**Target market:** Shelby County, Alabama (MVP)

---

## Architecture

```
[Scrapers] → [Raw Data Store] → [Normalizer] → [Signal Engine] → [Scoring Engine] → [API] → [Dashboard]
```

## Stack

| Layer | Tech |
|---|---|
| Backend API | Python 3.11, FastAPI |
| Database | PostgreSQL (Neon / Supabase on Vercel; Docker Compose locally) |
| ORM / Migrations | SQLAlchemy 2 (async) + Alembic |
| Serverless adapter | Mangum (ASGI → Lambda / Vercel) |
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Deployment | Vercel |

---

## Project Structure

```
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

### Start the backend

```bash
# From rse/
cp .env.example backend/.env
docker-compose -f infra/docker-compose.yml up -d

cd backend
pip install -r requirements.txt
alembic upgrade head
python main.py
```

API available at `http://localhost:8000`
Docs at `http://localhost:8000/docs`

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
   - `DATABASE_URL` — Neon or Supabase Postgres connection string
   - `APP_ENV` — `production`
   - `SCORING_VERSION` — `v1`
3. Deploy — Vercel routes `/api/*` to the Python function and `/*` to Next.js

---

## Build Progress

| Sprint | Tasks | Status |
|---|---|---|
| Sprint 1 | FastAPI + DB schema + address normalizer | ✅ Complete |
| Sprint 2 | CSV ingestion + absentee/long-term signals | ✅ Complete |
| Sprint 3 | SignalEngine + batch job + ScoringEngine | 🔄 In Progress |
| Sprint 4 | Lead API endpoints + unit tests | ⬜ Pending |
| Sprint 5 | Extensibility hooks + webhooks | ⬜ Pending |
