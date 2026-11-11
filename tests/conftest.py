"""Pytest umumiy fixturelari va izolyatsiyalangan test muhiti."""

import atexit
import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

_TMP_DIR = tempfile.TemporaryDirectory(prefix="uzmyjob_pytest_")
atexit.register(_TMP_DIR.cleanup)

_TEST_DB_PATH = Path(_TMP_DIR.name) / "pytest_uzmyjob.db"

# Real .env qiymatlarini va mahalliy bazani ishlatmaslik uchun test env sozlamalari
os.environ["POSTGRES_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH.as_posix()}"
os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())
os.environ["BOT_TOKEN"] = "123456789:TEST_BOT_TOKEN_PYTEST_ONLY"
os.environ["GEMINI_API_KEY"] = "test-gemini-key-pytest"
os.environ["WEBHOOK_URL"] = ""
os.environ["WEBHOOK_SECRET"] = ""
