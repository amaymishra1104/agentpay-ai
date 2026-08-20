# Architecture Foundation

## Current scope

This document defines only foundational structure for AgentPay.
Business flows and integrations are intentionally deferred to later steps.

## High-level components

- Frontend: Next.js + TypeScript + Tailwind
- Backend: FastAPI + Pydantic + SQLAlchemy
- Data: synthetic JSON merchant/product/customer/offer inputs
- Database: PostgreSQL via SQLAlchemy (Alembic planned for migrations)

## Security constraints

- Secrets must come from environment variables.
- Razorpay integration must run in TEST MODE.
- Backend secrets must never be exposed to frontend.
