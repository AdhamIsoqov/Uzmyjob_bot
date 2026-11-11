"""jobs.uz portali uchun scraper adapteri."""
import json
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from uzmyjob.adapters.base import ScraperAdapter
from uzmyjob.utils.logger import log


class JobsUzScraperAdapter(ScraperAdapter):
    """jobs.uz saytidan vakansiyalarni yig'ish adapteri (experimental stub)."""

    source_name: str = "jobs_uz"
    is_stub: bool = True
    BASE_URL: str = "https://jobs.uz/ru/vacancies"

    def __init__(
        self,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        rate_limit_delay: float = 1.0,
    ) -> None:
        super().__init__(rate_limit_delay=rate_limit_delay)
        self.user_agent = user_agent

    async def fetch(self) -> list[dict[str, Any]]:
        """jobs.uz vakansiyalar ro'yxatini oladi."""
        headers = {"User-Agent": self.user_agent}
        await self._rate_limit_wait()

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(self.BASE_URL, headers=headers)
                if resp.status_code != 200:
                    log.warning("jobs_uz_fetch_failed", status=resp.status_code)
                    return []

                html = resp.text
                vacancy_ids = set(re.findall(r"/vacancies/view/(\d+)", html))

                items = [
                    {
                        "id": vid,
                        "url": f"https://jobs.uz/ru/vacancies/view/{vid}",
                        "title": f"Vakansiya #{vid} (jobs.uz)",
                        "company": "jobs.uz",
                    }
                    for vid in list(vacancy_ids)[:15]
                ]

                log.info("jobs_uz_fetch_success", count=len(items))
                return items

        except Exception as exc:
            log.error("jobs_uz_fetch_exception", error=str(exc))
            return []

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """jobs.uz raw ma'lumotini standart Vacancy dict ga aylantirish."""
        return {
            "source": self.source_name,
            "external_id": str(raw.get("id")),
            "title": raw.get("title", "Vakansiya"),
            "company": raw.get("company", "jobs.uz"),
            "city": raw.get("city", "Toshkent"),
            "salary_min": raw.get("salary_min"),
            "salary_max": raw.get("salary_max"),
            "currency": raw.get("currency", "UZS"),
            "description": raw.get("description", "Batafsil jobs.uz portalida"),
            "url": raw.get("url", ""),
            "contact_phone": raw.get("phone"),
            "contact_telegram": raw.get("telegram"),
            "contact_email": raw.get("email"),
            "raw_data": json.dumps(raw, ensure_ascii=False),
            "published_at": datetime.now(UTC),
        }
