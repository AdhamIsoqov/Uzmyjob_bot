"""Konfiguratsiya va runtime validatsiya testlari."""

import pytest
from cryptography.fernet import Fernet

from uzmyjob.config import Settings


def _make_settings(**overrides) -> Settings:
    valid_key = Fernet.generate_key().decode()
    defaults = {
        "_env_file": None,
        "bot_token": "999999:VALID_TEST_TOKEN",
        "fernet_key": valid_key,
        "postgres_url": "sqlite+aiosqlite:///:memory:",
        "webhook_url": "",
        "webhook_secret": "",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_validate_runtime_accepts_valid_config():
    """To'g'ri BOT_TOKEN, FERNET_KEY va webhook sozlamalarida xato chiqmasligi kerak."""
    cfg = _make_settings(
        webhook_url="https://uzmyjob.onrender.com/",
        webhook_secret="strong-secret-token-123456",
    )
    cfg.validate_runtime()
    assert cfg.normalized_webhook_url == "https://uzmyjob.onrender.com/webhook"
    assert cfg.clean_webhook_secret == "strong-secret-token-123456"


@pytest.mark.parametrize("bad_token", ["", "your_bot_token", "your_telegram_bot_token"])
def test_validate_runtime_rejects_missing_or_placeholder_token(bad_token: str):
    """Bo'sh yoki placeholder BOT_TOKEN rad etilishi kerak."""
    cfg = _make_settings(bot_token=bad_token)
    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        cfg.validate_runtime()


@pytest.mark.parametrize("bad_key", ["", "not-a-fernet-key", "short"])
def test_validate_runtime_rejects_invalid_fernet_key(bad_key: str):
    """Bo'sh yoki noto'g'ri FERNET_KEY ishga tushishda rad etilishi kerak."""
    cfg = _make_settings(fernet_key=bad_key)
    with pytest.raises(RuntimeError, match="FERNET_KEY"):
        cfg.validate_runtime()


def test_validate_runtime_requires_strong_webhook_secret():
    """WEBHOOK_URL berilganda 16 belgidan qisqa secret rad etilishi kerak."""
    cfg_short = _make_settings(
        webhook_url="https://uzmyjob.onrender.com",
        webhook_secret="short",
    )
    with pytest.raises(RuntimeError, match="WEBHOOK_SECRET"):
        cfg_short.validate_runtime()


def test_normalized_webhook_url_avoids_double_suffix():
    """URL oxiridagi /webhook takrorlanmasligi kerak."""
    cfg = _make_settings(webhook_url="https://uzmyjob.onrender.com/webhook/")
    assert cfg.normalized_webhook_url == "https://uzmyjob.onrender.com/webhook"


def test_clean_webhook_secret_strips_disallowed_chars():
    """Webhook secret faqat Telegram ruxsat bergan belgilarni qoldiradi."""
    cfg = _make_settings(webhook_secret="abc$123_XYZ-def!@#")
    assert cfg.clean_webhook_secret == "abc123_XYZ-def"


def test_render_database_url_conversion(monkeypatch):
    """postgres:// URL avtomatik postgresql+asyncpg:// ga o'girilishi kerak."""
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host:5432/dbname")
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    cfg = Settings(_env_file=None, fernet_key=Fernet.generate_key().decode(), bot_token="123:abc")
    assert cfg.postgres_url.startswith("postgresql+asyncpg://")
