from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _CONFIG_DIR.parent
_ROOT_DIR = _BACKEND_DIR.parent

_ENV_FILES = (
    str(_BACKEND_DIR / ".env"),
    str(_ROOT_DIR / ".env"),
    str(_ROOT_DIR / "backend" / ".env"),
    ".env",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------------------------------------------------------
    # Application
    # ---------------------------------------------------------

    app_name: str = Field(
        default="AgentPay Backend",
        alias="APP_NAME",
    )

    app_env: str = Field(
        default="development",
        alias="APP_ENV",
    )

    log_level: str = Field(
        default="INFO",
        alias="LOG_LEVEL",
    )

    api_v1_prefix: str = Field(
        default="/api/v1",
        alias="API_V1_PREFIX",
    )

    frontend_origin: str = Field(
        default="http://localhost:3000",
        alias="FRONTEND_ORIGIN",
    )

    # ---------------------------------------------------------
    # Database
    # ---------------------------------------------------------

    database_url: str = Field(
        default="sqlite:///./agentpay.db",
        alias="DATABASE_URL",
    )

    # ---------------------------------------------------------
    # Cart / Shipping
    # ---------------------------------------------------------

    shipping_free_threshold_inr: int = Field(
        default=5000,
        alias="SHIPPING_FREE_THRESHOLD_INR",
    )

    shipping_flat_rate_inr: int = Field(
        default=150,
        alias="SHIPPING_FLAT_RATE_INR",
    )

    # ---------------------------------------------------------
    # LLM
    # ---------------------------------------------------------

    llm_provider: str = Field(
        default="mock",
        alias="LLM_PROVIDER",
    )

    groq_api_key: str | None = Field(
        default=None,
        alias="GROQ_API_KEY",
    )

    groq_model: str = Field(
        default="openai/gpt-oss-120b",
        alias="GROQ_MODEL",
    )

    openai_api_key: str | None = Field(
        default=None,
        alias="OPENAI_API_KEY",
    )

    anthropic_api_key: str | None = Field(
        default=None,
        alias="ANTHROPIC_API_KEY",
    )

    # ---------------------------------------------------------
    # Razorpay
    # ---------------------------------------------------------

    razorpay_mode: str = Field(
        default="test",
        alias="RAZORPAY_MODE",
    )

    razorpay_key_id: str | None = Field(
        default=None,
        alias="RAZORPAY_KEY_ID",
    )

    razorpay_key_secret: str | None = Field(
        default=None,
        alias="RAZORPAY_KEY_SECRET",
    )

    # ---------------------------------------------------------
    # Webhooks
    # ---------------------------------------------------------

    webhook_secret: str | None = Field(
        default=None,
        alias="WEBHOOK_SECRET",
    )

    # ---------------------------------------------------------
    # Security & Spending Limits
    # ---------------------------------------------------------

    session_secret: str = Field(
        default="agentpay_secure_session_secret_key_2026",
        alias="SESSION_SECRET",
    )

    session_expiry_seconds: int = Field(
        default=86400,
        alias="SESSION_EXPIRY_SECONDS",
    )

    max_transaction_inr: int = Field(
        default=80000,
        alias="MAX_TRANSACTION_INR",
    )

    daily_spend_limit_inr: int = Field(
        default=200000,
        alias="DAILY_SPEND_LIMIT_INR",
    )

    confirmation_expiry_seconds: int = Field(
        default=900,
        alias="CONFIRMATION_EXPIRY_SECONDS",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()