"""OLX.uz ish bo'limi scraper adapteri."""
import json
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from uzmyjob.adapters.base import ScraperAdapter
from uzmyjob.utils.logger import log


class OLXScraperAdapter(ScraperAdapter):
    """OLX.uz ish rukni orqali vakansiyalarni yig'ish adapteri (experimental stub)."""

    source_name: str = "olx"
    is_stub: bool = True
    BASE_URL: str = "https://www.olx.uz/rabota/it-telekom-kompyutery/"

    def __init__(
        self,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        rate_limit_delay: float = 1.0,
    ) -> None:
        super().__init__(rate_limit_delay=rate_limit_delay)
        self.user_agent = user_agent

    async def fetch(self, category_url: str | None = None) -> list[dict[str, Any]]:
        """OLX.uz sahifasini o'qib, e'lonlar ro'yxatini qaytaradi."""
        url = category_url or self.BASE_URL
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "uz,ru;q=0.9,en;q=0.8",
        }

        await self._rate_limit_wait()
        items: list[dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    log.warning("olx_fetch_failed", status=resp.status_code)
                    return []

                html = resp.text
                ad_links = set(re.findall(r'href="(/d/[^"]+)"', html))

                for link in list(ad_links)[:15]:
                    full_url = f"https://www.olx.uz{link}" if link.startswith("/") else link
                    ext_id_match = re.search(r"-ID([a-zA-Z0-9]+)\.html", link)
                    external_id = ext_id_match.group(1) if ext_id_match else link
                    slug_title = link.rsplit("/", 1)[-1].split("-ID")[0].replace("-", " ").strip()

                    items.append({
                        "id": external_id,
                        "url": full_url,
                        "title": slug_title.title() if slug_title else "IT Mutaxassis (OLX)",
                        "city": "Toshkent",
                        "raw_html_snippet": link,
                    })

                log.info("olx_fetch_success", count=len(items))
                return items

        except Exception as exc:
            log.error("olx_fetch_exception", error=str(exc))
            return []

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """OLX xom ma'lumotini standart Vacancy dict ga aylantirish."""
        return {
            "source": self.source_name,
            "external_id": str(raw.get("id")),
            "title": raw.get("title", "IT Vakansiya"),
            "company": raw.get("company", "OLX E'lon beruvchi"),
            "city": raw.get("city", "Toshkent"),
            "salary_min": raw.get("salary_min"),
            "salary_max": raw.get("salary_max"),
            "currency": raw.get("currency", "UZS"),
            "description": raw.get("description", "Batafsil OLX e'lonida"),
            "url": raw.get("url", ""),
            "contact_phone": raw.get("phone"),
            "contact_telegram": raw.get("telegram"),
            "contact_email": raw.get("email"),
            "raw_data": json.dumps(raw, ensure_ascii=False),
            "published_at": datetime.now(UTC),
        }
