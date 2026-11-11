"""Adapter base interface va umumiy rate-limiting mexanizmi."""
import asyncio
import time
from abc import ABC, abstractmethod


class ScraperAdapter(ABC):
    """Har bir manba uchun asosiy interfeys."""

    source_name: str = ""
    is_stub: bool = False

    def __init__(self, rate_limit_delay: float = 1.0) -> None:
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time: float = 0.0

    async def _rate_limit_wait(self) -> None:
        """Rate limitga rioya qilish (sukut bo'yicha max 1 req/sek)."""
        if self.rate_limit_delay <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.monotonic()

    @abstractmethod
    async def fetch(self) -> list[dict]:
        """Manbadan yangi vakansiyalarni oladi (normalize qilinmagan raw dict list)."""

    @abstractmethod
    def normalize(self, raw: dict) -> dict:
        """Raw dict → standart vakansiya dict."""
