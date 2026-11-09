"""structlog sozlamasi — PII filtri va log rotatsiyasi bilan."""
import contextlib
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog

# Windows terminali uchun UTF-8 kodlashni ta'minlash
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PII_FIELDS = {
    "phone", "email", "cv_text", "password", "token", "secret",
    "fernet_key", "access_token", "refresh_token", "bot_token"
}


def _pii_filter(logger, method, event_dict):
    """Maxfiy shaxsiy ma'lumotlarni (PII) loglardan qirqib tashlash."""
    for field in PII_FIELDS:
        if field in event_dict:
            event_dict[field] = "***REDACTED***"
    return event_dict


def setup_logging(
    level: str = "INFO",
    log_file: str | None = "logs/uzmyjob.log",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> None:
    """
    Log tizimini sozlash:
    1. Konsolga JSON / standart formatda chiqarish.
    2. Agar log_file ko'rsatilgan bo'lsa, RotatingFileHandler orqali faylga yozish.
    3. PII ma'lumotlarini qirqish.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handlers.append(file_handler)

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=handlers,
        force=True,
    )

    structlog.configure(
        processors=[
            _pii_filter,
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger()
