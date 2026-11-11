"""Manbalar salomatligi (Health tracking) va xatoliklar (Dead-Letter) nazorati."""
from datetime import UTC, datetime

from sqlalchemy import select

from uzmyjob.models.base import AsyncSessionLocal
from uzmyjob.models.source import Source
from uzmyjob.utils.logger import log
from uzmyjob.utils.metrics import SOURCE_ERRORS_TOTAL


class SourceHealthTracker:
    """Har bir scraper manbasi holati va xatoliklarini qayd etuvchi tizim."""

    MAX_CONSECUTIVE_ERRORS = 3

    @classmethod
    async def record_success(cls, source_name: str) -> None:
        """Muvaffaqiyatli fetch bo'lganda statusni 'ok' ga o'rnatish va error_count ni nolga tushirish."""
        async with AsyncSessionLocal() as session:
            stmt = select(Source).where(Source.name == source_name)
            src = (await session.execute(stmt)).scalar_one_or_none()
            if not src:
                src = Source(name=source_name, error_count=0)
                session.add(src)

            src.status = "ok"
            src.error_count = 0
            src.last_error = None
            src.last_checked_at = datetime.now(UTC)
            await session.commit()

    @classmethod
    async def record_failure(cls, source_name: str, error_message: str) -> None:
        """Xatolik yuz berganda xatolar hisoblagichini xavfsiz oshirish."""
        SOURCE_ERRORS_TOTAL.labels(source=source_name).inc()
        async with AsyncSessionLocal() as session:
            stmt = select(Source).where(Source.name == source_name)
            src = (await session.execute(stmt)).scalar_one_or_none()
            if not src:
                src = Source(name=source_name, error_count=0)
                session.add(src)

            src.error_count = (src.error_count or 0) + 1
            src.last_error = error_message[:500]
            src.last_checked_at = datetime.now(UTC)

            if src.error_count >= cls.MAX_CONSECUTIVE_ERRORS:
                src.status = "error"
                log.warning(
                    "source_marked_as_unhealthy",
                    source=source_name,
                    error_count=src.error_count,
                    last_error=error_message[:200],
                )

            await session.commit()
