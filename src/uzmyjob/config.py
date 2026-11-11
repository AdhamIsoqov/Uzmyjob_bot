"""Loyiha sozlamalari — pydantic-settings orqali."""
import contextlib
import os
import re
from typing import Any

from cryptography.fernet import Fernet
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = ""
    hh_client_id: str = ""
    hh_client_secret: str = ""
    gemini_api_key: str = ""
    postgres_url: str = "postgresql+asyncpg://uzmyjob:password@localhost:5432/uzmyjob"
    port: int = 8080
    fernet_key: str = ""
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

            raw_port = data.get("port") or os.environ.get("PORT")
            if raw_port:
                with contextlib.suppress(ValueError, TypeError):
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

    @property
    def clean_webhook_secret(self) -> str:
        """Telegram Webhook secret_token faqat [A-Za-z0-9_-] belgilarni qabul qiladi."""
        if not self.webhook_secret:
            return ""
        cleaned = re.sub(r"[^A-Za-z0-9_-]", "", self.webhook_secret)
        return cleaned[:256]

    def validate_runtime(self) -> None:
        """Bot ishga tushishidan oldin majburiy maxfiy kalitlar va konfiguratsiyani tekshirish."""
        if not self.bot_token or self.bot_token in {"your_bot_token", "your_telegram_bot_token", "test_bot_token"}:
            raise RuntimeError("BOT_TOKEN sozlanmagan! Iltimos, .env yoki muhit o'zgaruvchisini kiriting.")

        if not self.fernet_key:
            raise RuntimeError(
                "FERNET_KEY majburiy! Yangi kalit yaratish: "
                "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        try:
            Fernet(self.fernet_key.encode())
        except Exception as exc:
            raise RuntimeError(
                "FERNET_KEY formati noto'g'ri! 32-bayt url-safe base64 kalit bo'lishi shart."
            ) from exc

        if self.webhook_url and len(self.clean_webhook_secret) < 16:
            raise RuntimeError(
                "WEBHOOK_SECRET webhook rejimida majburiy va kamida 16 ta [A-Za-z0-9_-] belgidan iborat bo'lishi kerak."
            )


settings = Settings()
