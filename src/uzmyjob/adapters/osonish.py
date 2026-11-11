"""OsonIsh (osonish.uz) rasmiy vakansiyalar API adapteri."""
import json
import re
from typing import Any

import httpx

from uzmyjob.adapters._parsing import (
    extract_contacts,
    normalize_city,
    parse_published_at,
    strip_html,
)
from uzmyjob.adapters.base import ScraperAdapter
from uzmyjob.utils.logger import log


class OsonIshAdapter(ScraperAdapter):
    """OsonIsh (Bandlik vazirligi portali) API orqali vakansiyalarni yig'ish adapteri."""

    source_name: str = "osonish"
    is_stub: bool = False
    BASE_URL: str = "https://osonish.uz/api/v1/vacancies"

    def __init__(
        self,
        user_agent: str = "UzMyJobBot/1.0 (https://github.com/AdhamIsoqov/Uzmyjob_bot)",
        rate_limit_delay: float = 1.0,
    ) -> None:
        super().__init__(rate_limit_delay=rate_limit_delay)
        self.user_agent = user_agent

    async def fetch(
        self,
        per_page: int = 30,
        page: int = 1,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        """osonish.uz API dan so'nggi vakansiyalar ro'yxatini oladi."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        params: dict[str, Any] = {"per_page": per_page, "page": page}
        if search:
            params["search"] = search

        await self._rate_limit_wait()

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(self.BASE_URL, headers=headers, params=params)
                if resp.status_code != 200:
                    log.warning("osonish_fetch_failed", status=resp.status_code)
                    return []

                payload = resp.json()
                data_block = payload.get("data") or {}
                items = data_block.get("data") if isinstance(data_block, dict) else []
                if not isinstance(items, list):
                    log.warning("osonish_unexpected_payload")
                    return []

                log.info("osonish_fetch_success", count=len(items), page=page)
                return items
        except Exception as exc:
            log.error("osonish_fetch_exception", error=str(exc))
            return []

    @staticmethod
    def _clean_phone(raw_phone: str | None) -> str | None:
        if not raw_phone:
            return None
        digits = re.sub(r"\D", "", raw_phone)
        if len(digits) < 9:
            return None
        return f"+{digits}" if digits.startswith("998") else raw_phone.strip()

    @staticmethod
    def _coerce_salary(value: Any) -> int | None:
        try:
            num = int(float(value))
            return num if num > 0 else None
        except (TypeError, ValueError):
            return None

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """osonish.uz JSON obyektini standart Vacancy dict ga aylantirish."""
        ext_id = str(raw.get("id") or "")
        mmk_pos = raw.get("mmk_position") or {}
        title = (
            (raw.get("title") or mmk_pos.get("position_name") or "Vakansiya").strip()
        )

        company_obj = raw.get("company")
        if isinstance(company_obj, dict):
            company = (company_obj.get("name") or "OsonIsh Ish beruvchi").strip()
        elif isinstance(company_obj, str) and company_obj.strip():
            company = company_obj.strip()
        else:
            company = "OsonIsh Ish beruvchi"

        filial = raw.get("filial") or {}
        region_obj = filial.get("region") if isinstance(filial, dict) else None
        raw_city = (
            raw.get("city")
            or (region_obj.get("name_uz") if isinstance(region_obj, dict) else None)
            or raw.get("address")
        )
        city = normalize_city(raw_city, default="O'zbekiston")

        desc_parts: list[str] = []
        info_text = strip_html(raw.get("info") or raw.get("description"))
        if info_text:
            desc_parts.append(info_text)

        skills = raw.get("skills_details") or []
        if isinstance(skills, list):
            skill_names = [
                str(s.get("skill_name")).strip()
                for s in skills
                if isinstance(s, dict) and s.get("skill_name")
            ]
            if skill_names:
                desc_parts.append(f"Ko'nikmalar: {', '.join(skill_names)}")

        address = (raw.get("address") or "").strip()
        if address:
            desc_parts.append(f"Manzil: {address}")

        description = "\n".join(desc_parts) if desc_parts else title

        hr_obj = raw.get("hr") or {}
        phone = (
            self._clean_phone(raw.get("phone"))
            or self._clean_phone(hr_obj.get("phone") if isinstance(hr_obj, dict) else None)
            or self._clean_phone(raw.get("additional_phone"))
        )

        contacts = extract_contacts(f"{description}\n{raw.get('another_network') or ''}")
        telegram = raw.get("telegram") or (
            None if raw.get("is_hidden_network") else contacts["telegram"]
        )
        email = raw.get("email") or contacts["email"]

        return {
            "source": self.source_name,
            "external_id": ext_id,
            "title": title,
            "company": company,
            "city": city,
            "salary_min": self._coerce_salary(raw.get("min_salary") or raw.get("salary_min")),
            "salary_max": self._coerce_salary(raw.get("max_salary") or raw.get("salary_max")),
            "currency": raw.get("currency") or "UZS",
            "description": description,
            "url": raw.get("url") or f"https://osonish.uz/vacancies/{ext_id}",
            "contact_phone": phone or contacts["phone"],
            "contact_telegram": telegram,
            "contact_email": email,
            "raw_data": json.dumps(raw, ensure_ascii=False, default=str),
            "published_at": parse_published_at(raw.get("created_at") or raw.get("published_at")),
        }
