import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from contextlib import asynccontextmanager
from app.db.database import Base, engine, init_db
from app.api.routes import (
    agent,
    audit,
    auth,
    cart,
    catalog,
    checkout,
    health,
    webhooks,
)
from app.config import get_settings

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("agentpay")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database tables exist
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AgentPay backend foundation",
    lifespan=lifespan,
)


origins = [o.strip() for o in settings.frontend_origin.split(",") if o.strip()]
if settings.app_env.lower() == "development":
    for port in ("3000", "3001"):
        for host in ("localhost", "127.0.0.1"):
            url = f"http://{host}:{port}"
            if url not in origins:
                origins.append(url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_v1_prefix)
app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(catalog.router, prefix=settings.api_v1_prefix)
app.include_router(cart.router, prefix=settings.api_v1_prefix)
app.include_router(checkout.router, prefix=settings.api_v1_prefix)
app.include_router(agent.router, prefix=settings.api_v1_prefix)
app.include_router(audit.router, prefix=settings.api_v1_prefix)
app.include_router(webhooks.router, prefix=settings.api_v1_prefix)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server error on path %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
