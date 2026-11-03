"""Loyiha sozlamalari — pydantic-settings orqali."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = "test_bot_token"
    hh_client_id: str = ""
    hh_client_secret: str = ""
    gemini_api_key: str = "test_gemini_api_key"
    postgres_url: str = "postgresql+asyncpg://uzmyjob:password@localhost:5432/uzmyjob"
    fernet_key: str = "CiQQ5TdK3oXB28uTaTCCeTyGDcBekufPVlyQ7XKmMwM="
    sentry_dsn: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    webhook_url: str = ""
    webhook_secret: str = ""

    # Scheduler
    poll_interval_minutes: int = 15

    # Matching
    match_threshold: float = 0.55
    llm_rerank_threshold: float = 0.40
    gemini_monthly_cost_limit_usd: float = 5.0

    # Telegram anti-flood
    throttle_rate: int = 30  # msg/min per user


settings = Settings()
