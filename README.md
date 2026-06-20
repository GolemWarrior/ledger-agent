# Ledger Agent

A local-first personal finance tool that pulls transactions from Plaid, auto-categorizes them with an AI agent, and surfaces ambiguous ones for your review.

## Prerequisites

- Docker & Docker Compose
- A Plaid developer account (sandbox is free)
- An Anthropic API key

## Quick Start

```bash
cp .env.example .env
# Fill in your PLAID_CLIENT_ID, PLAID_SECRET, and ANTHROPIC_API_KEY in .env
docker compose up
```

- Backend API: http://localhost:8000
- Frontend:    http://localhost:5173
- API docs:    http://localhost:8000/docs

## Development

**Backend** (Python, managed with `uv`):
```bash
cd backend
uv sync
uvicorn ledger_agent.main:app --reload
```

**Frontend** (React + Vite):
```bash
cd frontend
npm install
npm run dev
```

**Database migrations** (Alembic):
```bash
cd backend
alembic upgrade head
```

## Architecture

- **Backend:** FastAPI + SQLAlchemy 2.x + Alembic + LangGraph
- **Frontend:** React 19 + Vite + TanStack Query + React Router + Tailwind CSS
- **Database:** PostgreSQL (public schema for live data, eval schema for eval runs)
- **Agent:** LangGraph with Postgres checkpointing (survives restarts)

See `_bmad-output/planning-artifacts/architecture.md` for full architecture decisions.
