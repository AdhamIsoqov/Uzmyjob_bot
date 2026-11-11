"""Freelance va masofaviy ishlar uchun RSS adapteri."""
import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any

import httpx

from uzmyjob.adapters.base import ScraperAdapter
from uzmyjob.utils.logger import log


class RSSFreelanceAdapter(ScraperAdapter):
    """RSS lentalari (masalan, Habr Freelance) orqali freelance buyurtmalarni olish."""

    source_name: str = "freelance_rss"

    def __init__(
        self,
        feed_urls: list[str] | None = None,
        rate_limit_delay: float = 1.0,
    ) -> None:
        super().__init__(rate_limit_delay=rate_limit_delay)
        self.feed_urls = feed_urls or [
            "https://freelance.habr.com/tasks.rss",
        ]

    async def fetch(self) -> list[dict[str, Any]]:
        """RSS lentalarini yuklab XML item'larini ajratadi."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) UzMyJobBot/1.0"
        }
        items: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for feed_url in self.feed_urls:
                await self._rate_limit_wait()
                try:
                    resp = await client.get(feed_url, headers=headers)
                    if resp.status_code != 200:
                        log.warning("rss_fetch_failed", url=feed_url, status=resp.status_code)
                        continue

                    root = ET.fromstring(resp.text)
                    channel = root.find("channel")
                    if channel is None:
                        continue

                    for item_elem in channel.findall("item")[:15]:
                        title = item_elem.findtext("title") or "Freelance vazifa"
                        link = item_elem.findtext("link") or ""
                        guid = item_elem.findtext("guid") or link
                        desc_raw = item_elem.findtext("description") or ""
                        clean_desc = re.sub(r"<[^>]+>", " ", desc_raw).strip()

                        items.append({
                            "id": guid,
                            "url": link,
                            "title": title,
                            "description": clean_desc,
                            "company": "Freelance Buyurtmachi",
                        })

                    log.info("rss_fetch_success", url=feed_url, count=len(items))

                except Exception as exc:
                    log.error("rss_fetch_exception", url=feed_url, error=str(exc))

        return items

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """RSS ma'lumotini standart Vacancy dict ga aylantirish."""
        return {
            "source": self.source_name,
            "external_id": str(raw.get("id")),
            "title": raw.get("title", "Freelance vazifa"),
            "company": raw.get("company", "Freelance"),
            "city": "Remote (Masofaviy)",
            "salary_min": None,
            "salary_max": None,
            "currency": "USD",
            "description": raw.get("description", ""),
            "url": raw.get("url", ""),
            "contact_phone": None,
            "contact_telegram": None,
            "contact_email": None,
            "raw_data": json.dumps(raw, ensure_ascii=False),
            "published_at": datetime.now(UTC),
        }
