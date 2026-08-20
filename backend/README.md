# Backend

FastAPI backend foundation for AgentPay.

## Run

1. Create and activate a virtual environment.
2. Install dependencies: `pip install -e .`
3. Copy `.env.example` to `.env` and update values.
4. Start API: `uvicorn app.main:app --reload`

Health endpoint:
- `GET /api/v1/health`
