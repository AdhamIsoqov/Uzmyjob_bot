"""UzJobs (uzjobs.uz) vakansiyalar portali RSS adapteri (source_name='jobs_uz')."""
import json
import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from uzmyjob.adapters._parsing import (
    extract_contacts,
    normalize_city,
    parse_published_at,
    parse_salary_text,
    strip_html,
)
from uzmyjob.adapters.base import ScraperAdapter
from uzmyjob.utils.logger import log


class JobsUzScraperAdapter(ScraperAdapter):
    """UzJobs (uzjobs.uz) RSS lentasi orqali O'zbekistondagi vakansiyalarni yig'ish adapteri.

    Eslatma: Legacy `jobs.uz` domeni DNS da mavjud emasligi sababli adapter
    faol `https://uzjobs.uz/rss_vak.cgi` rasmiy RSS oqimidan foydalanadi va
    bazadagi moslik uchun `source_name='jobs_uz'` ni saqlab qoladi.
    """

    source_name: str = "jobs_uz"
    is_stub: bool = False
    BASE_URL: str = "https://uzjobs.uz/rss_vak.cgi"

    def __init__(
        self,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) UzMyJobBot/1.0",
        rate_limit_delay: float = 1.0,
        feed_url: str | None = None,
    ) -> None:
        super().__init__(rate_limit_delay=rate_limit_delay)
        self.user_agent = user_agent
        self.feed_url = feed_url or self.BASE_URL

    @staticmethod
    def _decode_rss_xml(raw_bytes: bytes) -> ET.Element:
        """Windows-1251 yoki UTF-8 RSS baytlarini xavfsiz XML Element ga o'giradi."""
        head = raw_bytes[:200].decode("ascii", errors="ignore").lower()
        encoding = "cp1251" if "windows-1251" in head or "cp1251" in head else "utf-8"
        text = raw_bytes.decode(encoding, errors="replace")
        xml_utf8 = re.sub(
            r'(<\?xml[^?>]*encoding=["\'])[^"\']+(["\'])',
            r"\1utf-8\2",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
        return ET.fromstring(xml_utf8)

    @classmethod
    def parse_rss(cls, raw_bytes: bytes, limit: int = 30) -> list[dict[str, Any]]:
        """RSS XML baytlaridan tuzilgan vakansiya elementlarini ajratib oladi."""
        root = cls._decode_rss_xml(raw_bytes)
        channel = root.find("channel")
        if channel is None:
            return []

        items: list[dict[str, Any]] = []
        for elem in channel.findall("item")[:limit]:
            link = (elem.findtext("link") or "").strip()
            guid = (elem.findtext("guid") or link).strip()
            id_match = re.search(r"vakansy_view-(\d+)\.html", link or guid)
            external_id = id_match.group(1) if id_match else (guid or link)

            raw_title = (elem.findtext("title") or "").strip()
            title = re.sub(r"^(?:Вакансия|Vacancy):\s*", "", raw_title, flags=re.IGNORECASE).strip()
            title = title.rstrip(":").strip() or f"Vakansiya #{external_id}"

            raw_desc = elem.findtext("description") or ""
            clean_desc = strip_html(raw_desc)

            company_match = re.search(
                r"(?:Компания|Company):\s*(.+)", clean_desc, re.IGNORECASE
            )
            region_match = re.search(
                r"(?:Регион|Region):\s*(.+)", clean_desc, re.IGNORECASE
            )
            salary_match = re.search(
                r"(?:Предлагаемая зарплата|Salary offered):\s*(.+)",
                clean_desc,
                re.IGNORECASE,
            )

            company = company_match.group(1).strip() if company_match else "UzJobs"
            city = normalize_city(
                region_match.group(1).strip() if region_match else None,
                default="Toshkent",
            )
            sal_min, sal_max, currency = parse_salary_text(
                salary_match.group(1).strip() if salary_match else None
            )
            contacts = extract_contacts(clean_desc)

            items.append({
                "id": external_id,
                "url": link or f"https://uzjobs.uz/r/vakansy_view-{external_id}.html",
                "title": title,
                "company": company,
                "city": city,
                "salary_min": sal_min,
                "salary_max": sal_max,
                "currency": currency,
                "description": clean_desc or "Batafsil uzjobs.uz portalida",
                "phone": contacts["phone"],
                "telegram": contacts["telegram"],
                "email": contacts["email"],
                "published_at": (elem.findtext("pubDate") or "").strip() or None,
            })

        return items

    async def fetch(self, feed_url: str | None = None) -> list[dict[str, Any]]:
        """uzjobs.uz RSS lentasidan vakansiyalar ro'yxatini oladi."""
        target_url = feed_url or self.feed_url
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        }
        await self._rate_limit_wait()

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(target_url, headers=headers)
                if resp.status_code != 200:
                    log.warning("jobs_uz_fetch_failed", status=resp.status_code, url=target_url)
                    return []

                items = self.parse_rss(resp.content)
                log.info("jobs_uz_fetch_success", count=len(items))
                return items

        except Exception as exc:
            log.error("jobs_uz_fetch_exception", error=str(exc), url=target_url)
            return []

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """uzjobs.uz raw ma'lumotini standart Vacancy dict ga aylantirish."""
        return {
            "source": self.source_name,
            "external_id": str(raw.get("id", "")),
            "title": raw.get("title", "Vakansiya"),
            "company": raw.get("company", "UzJobs"),
            "city": normalize_city(raw.get("city"), default="Toshkent"),
            "salary_min": raw.get("salary_min"),
            "salary_max": raw.get("salary_max"),
            "currency": raw.get("currency"),
            "description": raw.get("description", "Batafsil uzjobs.uz portalida"),
            "url": raw.get("url", ""),
            "contact_phone": raw.get("phone"),
            "contact_telegram": raw.get("telegram"),
            "contact_email": raw.get("email"),
            "raw_data": json.dumps(raw, ensure_ascii=False, default=str),
            "published_at": parse_published_at(raw.get("published_at")),
        }
