"""Loyiha sozlamalari — pydantic-settings orqali."""
import contextlib
import os
from typing import Any

from pydantic import model_validator
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
    port: int = 8080
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

    @model_validator(mode="before")
    @classmethod
    def handle_render_environment(cls, data: Any) -> Any:
        """Render.com va boshqa bulut platformalarining muhit o'zgaruvchilarini moslashtirish."""
        if isinstance(data, dict):
            # 1. DATABASE_URL yoki POSTGRES_URL ni moslashtirish (asyncpg prefiksi)
            raw_db_url = (
                data.get("postgres_url")
                or data.get("database_url")
                or os.environ.get("DATABASE_URL")
                or os.environ.get("POSTGRES_URL")
            )
            if raw_db_url:
                if raw_db_url.startswith("postgres://"):
                    raw_db_url = raw_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
                elif raw_db_url.startswith("postgresql://") and "+asyncpg" not in raw_db_url:
                    raw_db_url = raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
                data["postgres_url"] = raw_db_url

            # 2. Render $PORT ni o'qish
            raw_port = data.get("port") or os.environ.get("PORT")
            if raw_port:
                with contextlib.suppress(Exception):
                    data["port"] = int(raw_port)

        return data

    @property
    def normalized_webhook_url(self) -> str:
        """Webhook URL da takrorlanish (/webhook/webhook) xatosini oldini olish."""
        if not self.webhook_url:
            return ""
        clean = self.webhook_url.strip().rstrip("/")
        if clean.endswith("/webhook"):
            return clean
        return f"{clean}/webhook"


settings = Settings()
