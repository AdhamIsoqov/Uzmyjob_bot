"""structlog sozlamasi — PII filtri bilan."""
import logging

import structlog

PII_FIELDS = {"phone", "email", "cv_text", "password", "token"}


def _pii_filter(logger, method, event_dict):
    for field in PII_FIELDS:
        if field in event_dict:
            event_dict[field] = "***REDACTED***"
    return event_dict


def setup_logging(level: str = "INFO") -> None:
    structlog.configure(
        processors=[
            _pii_filter,
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
    )


log = structlog.get_logger()
