"""OLX.uz ish bo'limi scraper adapteri."""
import json
import re
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


class OLXScraperAdapter(ScraperAdapter):
    """OLX.uz ish rukni uchun strukturalangan HTML/JSON-LD parser adapteri.

    Muhim: `www.olx.uz` Amazon CloudFront WAF orqali avtomatlashtirilgan HTTP
    so'rovlarini `403` javobi bilan cheklaydi va ochiq API taqdim etmaydi.
    Shuning uchun default pipeline'da `is_stub = True` holatida o'chirilgan;
    to'g'ridan-to'g'ri HTML yoki ruxsat etilgan manbadan chaqirilganda to'liq ishlaydi.
    """

    source_name: str = "olx"
    is_stub: bool = True
    BASE_URL: str = "https://www.olx.uz/rabota/it-telekom-kompyutery/"

    def __init__(
        self,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        rate_limit_delay: float = 1.0,
    ) -> None:
        super().__init__(rate_limit_delay=rate_limit_delay)
        self.user_agent = user_agent

    @staticmethod
    def _extract_id_from_url(url: str) -> str:
        ext_id_match = re.search(r"-ID([a-zA-Z0-9]+)\.html", url)
        return ext_id_match.group(1) if ext_id_match else url

    @classmethod
    def _parse_json_ld(cls, html_text: str) -> list[dict[str, Any]]:
        """Sahifadagi Schema.org JobPosting JSON-LD bloklaridan vakansiyalarni oladi."""
        results: list[dict[str, Any]] = []
        blocks = re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        def _collect_postings(node: Any) -> list[dict[str, Any]]:
            found: list[dict[str, Any]] = []
            if isinstance(node, list):
                for item in node:
                    found.extend(_collect_postings(item))
            elif isinstance(node, dict):
                node_type = node.get("@type")
                if node_type == "JobPosting":
                    found.append(node)
                if "@graph" in node:
                    found.extend(_collect_postings(node["@graph"]))
                if "itemListElement" in node:
                    for el in node.get("itemListElement") or []:
                        if isinstance(el, dict):
                            found.extend(_collect_postings(el.get("item") or el))
            return found

        for raw_block in blocks:
            try:
                parsed = json.loads(raw_block.strip())
            except json.JSONDecodeError:
                continue

            for job in _collect_postings(parsed):
                url = str(job.get("url") or "")
                org = job.get("hiringOrganization") or {}
                company = org.get("name") if isinstance(org, dict) else None
                loc = job.get("jobLocation") or {}
                if isinstance(loc, list) and loc:
                    loc = loc[0]
                addr = loc.get("address") if isinstance(loc, dict) else {}
                raw_city = addr.get("addressLocality") if isinstance(addr, dict) else None

                salary_obj = job.get("baseSalary") or {}
                sal_val = salary_obj.get("value") if isinstance(salary_obj, dict) else {}
                sal_min = sal_max = None
                curr = salary_obj.get("currency") if isinstance(salary_obj, dict) else None
                if isinstance(sal_val, dict):
                    sal_min = int(sal_val["minValue"]) if sal_val.get("minValue") else None
                    sal_max = int(sal_val["maxValue"]) if sal_val.get("maxValue") else sal_min
                elif isinstance(sal_val, (int, float)):
                    sal_min = sal_max = int(sal_val)

                desc = strip_html(str(job.get("description") or ""))
                contacts = extract_contacts(desc)
                results.append({
                    "id": cls._extract_id_from_url(url) or str(job.get("title") or ""),
                    "url": url,
                    "title": strip_html(str(job.get("title") or "")) or "OLX Vakansiya",
                    "company": company or "OLX E'lon beruvchi",
                    "city": normalize_city(raw_city, default="O'zbekiston"),
                    "salary_min": sal_min,
                    "salary_max": sal_max,
                    "currency": curr or ("UZS" if sal_min or sal_max else None),
                    "description": desc or "Batafsil OLX e'lonida",
                    "phone": contacts["phone"],
                    "telegram": contacts["telegram"],
                    "email": contacts["email"],
                    "published_at": job.get("datePosted"),
                })

        return results

    @classmethod
    def parse_html(cls, html_text: str, limit: int = 20) -> list[dict[str, Any]]:
        """OLX HTML sahifasidan JSON-LD yoki e'lon kartalarini tahlil qiladi."""
        ld_items = cls._parse_json_ld(html_text)
        if ld_items:
            return ld_items[:limit]

        items: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        card_parts = re.split(
            r'<div[^>]+data-cy=["\']l-card["\'][^>]*>',
            html_text,
            flags=re.IGNORECASE,
        )
        for block in card_parts[1 : limit + 1]:
            href_m = re.search(r'href=["\'](/d/[^"\']+|https://www\.olx\.uz/d/[^"\']+)["\']', block)
            if not href_m:
                continue
            link = href_m.group(1)
            full_url = f"https://www.olx.uz{link}" if link.startswith("/") else link
            ext_id = cls._extract_id_from_url(link)
            if ext_id in seen_ids:
                continue
            seen_ids.add(ext_id)

            title_m = re.search(r"<h[46][^>]*>(.*?)</h[46]>", block, flags=re.IGNORECASE | re.DOTALL)
            raw_title = strip_html(title_m.group(1)) if title_m else ""
            if not raw_title:
                raw_title = link.rsplit("/", 1)[-1].split("-ID")[0].replace("-", " ").strip().title()

            price_m = re.search(
                r'data-testid=["\']ad-price["\'][^>]*>(.*?)</p>',
                block,
                flags=re.IGNORECASE | re.DOTALL,
            )
            sal_min, sal_max, curr = parse_salary_text(strip_html(price_m.group(1)) if price_m else "")

            loc_m = re.search(
                r'data-testid=["\']location-date["\'][^>]*>(.*?)</p>',
                block,
                flags=re.IGNORECASE | re.DOTALL,
            )
            loc_raw = strip_html(loc_m.group(1)).split(" - ")[0] if loc_m else ""
            card_text = strip_html(block)
            contacts = extract_contacts(card_text)

            items.append({
                "id": ext_id,
                "url": full_url,
                "title": raw_title or "OLX Vakansiya",
                "city": normalize_city(loc_raw, default="O'zbekiston"),
                "salary_min": sal_min,
                "salary_max": sal_max,
                "currency": curr,
                "description": card_text or "Batafsil OLX e'lonida",
                "phone": contacts["phone"],
                "telegram": contacts["telegram"],
                "email": contacts["email"],
            })

        return items

    async def fetch(self, category_url: str | None = None) -> list[dict[str, Any]]:
        """OLX.uz sahifasini o'qib, e'lonlar ro'yxatini qaytaradi."""
        url = category_url or self.BASE_URL
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "uz,ru;q=0.9,en;q=0.8",
        }

        await self._rate_limit_wait()

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 403:
                    log.warning(
                        "olx_waf_blocked",
                        status=resp.status_code,
                        server=resp.headers.get("server", "unknown"),
                        url=url,
                    )
                    return []
                if resp.status_code != 200:
                    log.warning("olx_fetch_failed", status=resp.status_code, url=url)
                    return []

                items = self.parse_html(resp.text)
                log.info("olx_fetch_success", count=len(items))
                return items

        except Exception as exc:
            log.error("olx_fetch_exception", error=str(exc))
            return []

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """OLX xom ma'lumotini standart Vacancy dict ga aylantirish."""
        return {
            "source": self.source_name,
            "external_id": str(raw.get("id", "")),
            "title": raw.get("title", "OLX Vakansiya"),
            "company": raw.get("company", "OLX E'lon beruvchi"),
            "city": normalize_city(raw.get("city"), default="O'zbekiston"),
            "salary_min": raw.get("salary_min"),
            "salary_max": raw.get("salary_max"),
            "currency": raw.get("currency"),
            "description": raw.get("description", "Batafsil OLX e'lonida"),
            "url": raw.get("url", ""),
            "contact_phone": raw.get("phone"),
            "contact_telegram": raw.get("telegram"),
            "contact_email": raw.get("email"),
            "raw_data": json.dumps(raw, ensure_ascii=False, default=str),
            "published_at": parse_published_at(raw.get("published_at")),
        }
