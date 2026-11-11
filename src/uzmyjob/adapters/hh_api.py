"""hh.uz API adapter (ScraperAdapter implementation)."""
import asyncio
import json
from datetime import datetime
from typing import Any

import httpx

from uzmyjob.adapters.base import ScraperAdapter
from uzmyjob.utils.logger import log


class HeadHunterAdapter(ScraperAdapter):
    """hh.uz rasmiy API orqali vakansiyalarni qidirish va normallashtirish."""

    source_name: str = "hh"
    BASE_URL: str = "https://api.hh.uz"

    def __init__(
        self,
        user_agent: str = "UzMyJobBot/1.0 (dev@uzmyjob.local)",
        rate_limit_delay: float = 1.0,
    ) -> None:
        super().__init__(rate_limit_delay=rate_limit_delay)
        self.user_agent = user_agent

    async def fetch(
        self,
        text: str = "",
        area: str = "97",  # 97 = O'zbekiston
        per_page: int = 20,
        page: int = 0,
    ) -> list[dict[str, Any]]:
        """hh.uz dan yangi vakansiyalarni qidiradi (exponential backoff bilan 3 urinish)."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        params: dict[str, Any] = {
            "area": area,
            "per_page": per_page,
            "page": page,
            "order_by": "publication_time",
        }
        if text:
            params["text"] = text

        url = f"{self.BASE_URL}/vacancies"
        max_retries = 3
        backoff = 1.0

        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(1, max_retries + 1):
                try:
                    await self._rate_limit_wait()
                    response = await client.get(url, headers=headers, params=params)

                    if response.status_code == 200:
                        data = response.json()
                        items = data.get("items", [])
                        log.info("hh_fetch_success", count=len(items), page=page)
                        return items

                    if response.status_code in (429, 500, 502, 503, 504):
                        log.warning(
                            "hh_fetch_retryable_status",
                            status=response.status_code,
                            attempt=attempt,
                        )
                    else:
                        log.error(
                            "hh_fetch_failed",
                            status=response.status_code,
                            body=response.text[:200],
                        )
                        return []

                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    log.warning("hh_fetch_connection_error", error=str(exc), attempt=attempt)

                if attempt < max_retries:
                    await asyncio.sleep(backoff)
                    backoff *= 2

        log.error("hh_fetch_exhausted_retries", text=text, area=area)
        return []

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """hh.uz raw JSON ma'lumotini Vacancy modeliga mos dictga o'giradi."""
        salary_info = raw.get("salary") or {}
        area_info = raw.get("area") or {}
        employer = raw.get("employer") or {}
        snippet = raw.get("snippet") or {}
        req = snippet.get("requirement") or ""
        resp = snippet.get("responsibility") or ""
        description = f"Talablar: {req}\nMajburiyatlar: {resp}".strip()

        contacts = raw.get("contacts") or {}
        contact_phone = None
        phones = contacts.get("phones") or []
        if phones:
            p = phones[0]
            contact_phone = f"+{p.get('country')}{p.get('city')}{p.get('number')}"

        published_at = None
        pub_str = raw.get("published_at")
        if pub_str:
            try:
                published_at = datetime.fromisoformat(pub_str)
            except ValueError:
                published_at = None

        return {
            "source": self.source_name,
            "external_id": str(raw.get("id")),
            "title": raw.get("name", ""),
            "company": employer.get("name"),
            "city": area_info.get("name"),
            "salary_min": salary_info.get("from"),
            "salary_max": salary_info.get("to"),
            "currency": salary_info.get("currency"),
            "description": description,
            "url": raw.get("alternate_url", f"https://hh.uz/vacancy/{raw.get('id')}"),
            "contact_phone": contact_phone,
            "contact_telegram": None,
            "contact_email": contacts.get("email"),
            "raw_data": json.dumps(raw, ensure_ascii=False),
            "published_at": published_at,
        }
