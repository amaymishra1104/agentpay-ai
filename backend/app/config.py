from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="AgentPay Backend", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    frontend_origin: str = Field(default="http://localhost:3000", alias="FRONTEND_ORIGIN")

    database_url: str = Field(
        default="sqlite:///./agentpay.db",
        alias="DATABASE_URL",
    )

    shipping_free_threshold_inr: int = Field(default=5000, alias="SHIPPING_FREE_THRESHOLD_INR")
    shipping_flat_rate_inr: int = Field(default=150, alias="SHIPPING_FLAT_RATE_INR")

    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    razorpay_mode: str = Field(default="test", alias="RAZORPAY_MODE")
    razorpay_key_id: str | None = Field(default=None, alias="RAZORPAY_KEY_ID")
    razorpay_key_secret: str | None = Field(default=None, alias="RAZORPAY_KEY_SECRET")

    webhook_secret: str | None = Field(default=None, alias="WEBHOOK_SECRET")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
