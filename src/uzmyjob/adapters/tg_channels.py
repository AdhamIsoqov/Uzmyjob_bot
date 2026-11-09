"""Ochiq Telegram kanallari (t.me/s/...) dan vakansiyalarni yig'ish adapteri."""
import asyncio
import html
import json
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from uzmyjob.adapters.base import ScraperAdapter
from uzmyjob.utils.logger import log


class TelegramChannelAdapter(ScraperAdapter):
    """Telegram ochiq kanallaridagi (masalan UstozShogird, rabota_tashkent, it_jobs_uz) e'lonlarni o'qish adapteri."""

    source_name: str = "tg_channel"

    def __init__(
        self,
        channels: list[str] | None = None,
        rate_limit_delay: float = 1.0,
    ):
        # Asosiy faol ish kanallari ro'yxati
        self.channels = channels or [
            "it_jobs_uz",
            "rabota_tashkent",
            "UstozShogird",
            "rabota_uz",
            "vakansii_uz",
        ]
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time: float = 0.0

    async def _rate_limit_wait(self) -> None:
        """1 req/sek qoidasi."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def fetch(self) -> list[dict[str, Any]]:
        """Barcha belgilangan kanallarning t.me/s/<kanal> veb-versiyasidan e'lonlarni oladi."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        }
        all_posts: list[dict[str, Any]] = []

        for ch in self.channels:
            url = f"https://t.me/s/{ch}"
            await self._rate_limit_wait()

            try:
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code != 200:
                        log.warning("tg_channel_fetch_failed", channel=ch, status=resp.status_code)
                        continue

                    page_html = resp.text
                    # Post bloklarini topamiz
                    # data-post="channel/12345"
                    posts = re.findall(
                        r'data-post="([^"]+)".*?tgme_widget_message_text[^>]*>(.*?)</div>',
                        page_html,
                        re.DOTALL,
                    )

                    for post_id, text_html in posts[-25:]:  # Eng so'nggi 25 ta post
                        clean_text = re.sub(r"<[^>]+>", " ", text_html).strip()
                        clean_text = html.unescape(clean_text)
                        clean_text = re.sub(r"[ \t\xa0]+", " ", clean_text)
                        txt_lower = clean_text.lower()

                        # 1. Nomzodning o'zi ish qidirayotgan bo'lsa (rezyume) yoki o'quv/shogirdlik bo'lsa, o'tkazib yuboramiz
                        is_candidate = any(
                            marker in txt_lower
                            for marker in [
                                "ish joyi kerak",
                                "ish qidiryapman",
                                "ish qidirmoqdaman",
                                "ish qidirayapman",
                                "shogird kerak",
                                "ustoz kerak",
                                "sherik kerak",
                                "rezyume",
                                "резюме",
                                "ищу работу",
                                "ищу заказ",
                                "ищу стажировку",
                                "#ishjoyikerak",
                                "#shogird",
                                "#ustoz",
                                "#sherik",
                                "kasbi:",
                                "maqsad:",
                                "burger king",
                                "добро пожаловать в канал",
                                "bo'sh ish o'rinlarini ochish",
                            ]
                        )
                        if is_candidate:
                            continue

                        # UstozShogird da "Xodim: <ism>" ko'rinishida nomzod rezyumesi bo'lsa
                        if re.search(r"\bxodim:\s*[a-zа-яa-z]", txt_lower):
                            continue

                        # Agar UstozShogird kanali bo'lsa, faqat aniq ish beruvchi e'lonlarini olamiz
                        if ch.lower() == "ustozshogird" and not any(k in txt_lower for k in ["xodim kerak", "#xodimkerak", "#ishjoyi", "idora:"]):
                            continue

                        # 2. Agar post ish beruvchining vakansiyasi bo'lsa
                        if any(kw in txt_lower for kw in ["xodim", "vakansiya", "ish", "developer", "dasturchi", "menejer", "mutaxassis", "operat", "administrator", "qidirilmoqda", "talab", "hiring", "looking for", "требуется"]):
                            # Telegram kontaktni ajratish (@username)
                            tg_contact = None
                            tg_match = re.search(r"@([a-zA-Z0-9_]{4,})", clean_text)
                            if tg_match:
                                tg_contact = f"@{tg_match.group(1)}"

                            # Telefon raqamini ajratish
                            phone = None
                            phone_match = re.search(r"(\+?998[\d\s-]{9,})", clean_text)
                            if phone_match:
                                phone = phone_match.group(1).replace(" ", "").replace("-", "")

                            # Kompaniya nomini ajratish
                            company = None
                            m_comp = re.search(r"(?:Idora|Компания|Работодатель):\s*([^\n\r📋▫️—]+)", clean_text, re.IGNORECASE)
                            if m_comp:
                                comp_clean = m_comp.group(1).strip()
                                comp_clean = re.split(r"(?:Сайт|Контакт|Aloqa|Telegram|📞|✈️)", comp_clean, flags=re.IGNORECASE)[0].strip()
                                if len(comp_clean) > 2:
                                    company = comp_clean

                            # Sarlavhani ajratish
                            lines = [line.strip() for line in clean_text.split("\n") if len(line.strip()) > 2]
                            title = None
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
                                elif len(first) < 70 and not any(k in first.lower() for k in ["xodim kerak", "elon", "ishga taklif"]):
                                    title = first

                            if not title:
                                m_vac = re.search(r"(?:Вакансия|Lavozim|Position|В поисках):\s*([^\n\r]+)", clean_text, re.IGNORECASE)
                                if m_vac:
                                    title = m_vac.group(1).strip()
                                elif "texnologiya:" in txt_lower:
                                    m_tech = re.search(r"Texnologiya:\s*([^\n\r]+)", clean_text, re.IGNORECASE)
                                    if m_tech:
                                        title = f"IT Mutaxassis ({m_tech.group(1).strip()[:40]})"
                                else:
                                    title = lines[0][:80] if lines else f"Vakansiya ({ch})"

                            # Sarlavhani tozalash
                            title = re.sub(r"^(?:Вакансия|Lavozim|Position|В поисках):\s*", "", title, flags=re.IGNORECASE).strip()
                            title = re.split(r"(?:Компания|Работодатель|Idora|Сайт|Maosh|Зарплата|Oylik)", title, flags=re.IGNORECASE)[0].strip()

                            all_posts.append({
                                "id": post_id,
                                "channel": ch,
                                "url": f"https://t.me/{post_id}",
                                "title": title[:100],
                                "company": company or f"Telegram: @{ch}",
                                "description": clean_text,
                                "telegram": tg_contact,
                                "phone": phone,
                            })

                    log.info("tg_channel_fetch_success", channel=ch, count=len(all_posts))

            except Exception as e:
                log.error("tg_channel_exception", channel=ch, error=str(e))

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
                pass

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
