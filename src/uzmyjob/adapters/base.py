"""Adapter base interface."""
from abc import ABC, abstractmethod


class ScraperAdapter(ABC):
    """Har bir manba uchun asosiy interfeys."""

    source_name: str = ""

    @abstractmethod
    async def fetch(self) -> list[dict]:
        """
        Manbadan yangi vakansiyalarni oladi.
        Returns: raw dict list (normalize qilinmagan).
        Max 1 req/sek!
        """

    @abstractmethod
    def normalize(self, raw: dict) -> dict:
        """Raw dict → standart vakansiya dict."""
