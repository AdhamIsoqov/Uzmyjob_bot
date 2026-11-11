"""Ochiq Telegram kanallari (t.me/s/...) dan vakansiyalarni yig'ish adapteri."""
import html
import json
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from uzmyjob.adapters.base import ScraperAdapter
from uzmyjob.utils.filters import is_candidate_resume
from uzmyjob.utils.logger import log

VACANCY_KEYWORDS = (
    "xodim", "vakansiya", "ish", "developer", "dasturchi", "menejer",
    "mutaxassis", "operat", "administrator", "qidirilmoqda", "talab",
    "hiring", "looking for", "требуется",
)


class TelegramChannelAdapter(ScraperAdapter):
    """Telegram ochiq kanallaridagi e'lonlarni o'qish adapteri."""

    source_name: str = "tg_channel"

    def __init__(
        self,
        channels: list[str] | None = None,
        rate_limit_delay: float = 1.0,
    ) -> None:
        super().__init__(rate_limit_delay=rate_limit_delay)
        self.channels = channels or [
            "it_jobs_uz",
            "rabota_tashkent",
            "UstozShogird",
            "rabota_uz",
            "vakansii_uz",
        ]

    @staticmethod
    def _extract_title(clean_text: str, channel: str) -> str:
        lines = [line.strip() for line in clean_text.split("\n") if len(line.strip()) > 2]
        title: str | None = None
        if lines:
            first = lines[0]
            if "работодатель" in first.lower():
                parts = re.split(r"работодатель", first, flags=re.IGNORECASE)
                if len(parts[0].strip()) > 2:
                    title = parts[0].strip()
            elif "idora" in first.lower():
                parts = re.split(r"idora", first, flags=re.IGNORECASE)
                if len(parts[0].strip()) > 2:
                    title = parts[0].strip()
            elif len(first) < 70 and not any(
                k in first.lower() for k in ("xodim kerak", "elon", "ishga taklif")
            ):
                title = first

        if not title:
            m_vac = re.search(
                r"(?:Вакансия|Lavozim|Position|В поисках):\s*([^\n\r]+)", clean_text, re.IGNORECASE
            )
            if m_vac:
                title = m_vac.group(1).strip()
            elif "texnologiya:" in clean_text.lower():
                m_tech = re.search(r"Texnologiya:\s*([^\n\r]+)", clean_text, re.IGNORECASE)
                if m_tech:
                    title = f"IT Mutaxassis ({m_tech.group(1).strip()[:40]})"
            else:
                title = lines[0][:80] if lines else f"Vakansiya ({channel})"

        title = re.sub(
            r"^(?:Вакансия|Lavozim|Position|В поисках):\s*", "", title, flags=re.IGNORECASE
        ).strip()
        title = re.split(
            r"(?:Компания|Работодатель|Idora|Сайт|Maosh|Зарплата|Oylik)", title, flags=re.IGNORECASE
        )[0].strip()
        return (title or f"Vakansiya ({channel})")[:100]

    async def fetch(self) -> list[dict[str, Any]]:
        """Barcha belgilangan kanallarning t.me/s/<kanal> veb-versiyasidan e'lonlarni oladi."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        }
        all_posts: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for ch in self.channels:
                url = f"https://t.me/s/{ch}"
                await self._rate_limit_wait()

                try:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code != 200:
                        log.warning("tg_channel_fetch_failed", channel=ch, status=resp.status_code)
                        continue

                    posts = re.findall(
                        r'data-post="([^"]+)".*?tgme_widget_message_text[^>]*>(.*?)</div>',
                        resp.text,
                        re.DOTALL,
                    )

                    ch_count = 0
                    for post_id, text_html in posts[-25:]:
                        text_with_breaks = re.sub(r"<br\s*/?>", "\n", text_html, flags=re.IGNORECASE)
                        clean_text = re.sub(r"<[^>]+>", " ", text_with_breaks).strip()
                        clean_text = html.unescape(clean_text)
                        clean_text = re.sub(r"[ \t\xa0]+", " ", clean_text)
                        txt_lower = clean_text.lower()

                        if is_candidate_resume("", clean_text) or "maqsad:" in txt_lower:
                            continue

                        if ch.lower() == "ustozshogird" and not any(
                            k in txt_lower for k in ("xodim kerak", "#xodimkerak", "#ishjoyi", "idora:")
                        ):
                            continue

                        if not any(kw in txt_lower for kw in VACANCY_KEYWORDS):
                            continue

                        tg_match = re.search(r"@([a-zA-Z0-9_]{4,})", clean_text)
                        tg_contact = f"@{tg_match.group(1)}" if tg_match else None

                        phone_match = re.search(r"(\+?998[\d\s-]{9,})", clean_text)
                        phone = (
                            phone_match.group(1).replace(" ", "").replace("-", "")
                            if phone_match
                            else None
                        )

                        company = None
                        m_comp = re.search(
                            r"(?:Idora|Компания|Работодатель):\s*([^\n\r📋▫️—]+)",
                            clean_text,
                            re.IGNORECASE,
                        )
                        if m_comp:
                            comp_clean = re.split(
                                r"(?:Сайт|Контакт|Aloqa|Telegram|📞|✈️)",
                                m_comp.group(1).strip(),
                                flags=re.IGNORECASE,
                            )[0].strip()
                            if len(comp_clean) > 2:
                                company = comp_clean

                        all_posts.append({
                            "id": post_id,
                            "channel": ch,
                            "url": f"https://t.me/{post_id}",
                            "title": self._extract_title(clean_text, ch),
                            "company": company or f"Telegram: @{ch}",
                            "description": clean_text,
                            "telegram": tg_contact,
                            "phone": phone,
                        })
                        ch_count += 1

                    log.info("tg_channel_fetch_success", channel=ch, count=ch_count)

                except Exception as exc:
                    log.error("tg_channel_exception", channel=ch, error=str(exc))

        return all_posts

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Telegram kanal postini standart Vacancy dict ga aylantirish."""
        desc = raw.get("description", "")
        city = "O'zbekiston"
        if re.search(r"\b(toshkent|ташкент|tashkent)\b", desc, re.IGNORECASE):
            city = "Toshkent"
        elif re.search(r"\b(samarqand|самарканд)\b", desc, re.IGNORECASE):
            city = "Samarqand"
        elif re.search(r"\b(remote|masofaviy|удаленка)\b", desc, re.IGNORECASE):
            city = "Masofaviy"

        salary_min, salary_max, currency = None, None, None
        sal_match = re.search(r"(\d[\d\s]{2,}\d)\s*(so'?m|сум|\$|usd)", desc, re.IGNORECASE)
        if sal_match:
            raw_num = re.sub(r"\s+", "", sal_match.group(1))
            curr_str = sal_match.group(2).lower()
            currency = "USD" if "$" in curr_str or "usd" in curr_str else "UZS"
            try:
                salary_min = int(raw_num)
            except ValueError:
                salary_min = None

        return {
            "source": self.source_name,
            "external_id": str(raw.get("id")),
            "title": raw.get("title", "Telegram Vakansiya"),
            "company": raw.get("company") or f"Telegram: @{raw.get('channel', 'kanal')}",
            "city": city,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "currency": currency,
            "description": desc,
            "url": raw.get("url", ""),
            "contact_phone": raw.get("phone"),
            "contact_telegram": raw.get("telegram"),
            "contact_email": None,
            "raw_data": json.dumps(raw, ensure_ascii=False),
            "published_at": datetime.now(UTC),
        }
