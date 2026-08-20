# AgentPay - AI-Native Commerce Agent

Production-quality prototype foundation for Razorpay AI Buildathon 2026 (Track 1: AI Growth & Agentic Commerce).

## Scope of this step

This repository currently contains only foundational scaffolding:
- Monorepo folder layout for frontend, backend, data, and docs
- Next.js + TypeScript + Tailwind project foundation
- FastAPI + Pydantic + SQLAlchemy + Alembic backend foundation
- Environment variable templates
- Initial synthetic data files
- Basic health endpoint

Not implemented in this step:
- Agent orchestration logic
- Razorpay payment workflow
- Checkout policy execution flow
- Full dashboard UI

## Repository layout

- `frontend/`: Next.js application foundation
- `backend/`: FastAPI service foundation
- `data/`: Synthetic merchants, products, customers, offers
- `docs/`: Architecture and security notes

## Quick start

### Frontend

1. `cd frontend`
2. `npm install`
3. `npm run dev`

### Backend

1. `cd backend`
2. Create and activate a virtual environment
3. `pip install -e .`
4. Copy `.env.example` to `.env` and set values
5. `uvicorn app.main:app --reload`

Health check:
- `GET http://127.0.0.1:8000/api/v1/health`
