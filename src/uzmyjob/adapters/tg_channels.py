"""Ochiq Telegram kanallari (t.me/s/...) dan vakansiyalarni yig'ish adapteri."""
import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from uzmyjob.adapters.base import ScraperAdapter
from uzmyjob.utils.logger import log


class TelegramChannelAdapter(ScraperAdapter):
    """Telegram ochiq kanallaridagi (masalan UstozShogird) e'lonlarni o'qish adapteri."""

    source_name: str = "tg_channel"

    def __init__(
        self,
        channels: list[str] | None = None,
        rate_limit_delay: float = 1.0,
    ):
        # Default kanallar ro'yxati
        self.channels = channels or ["UstozShogird"]
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

                    html = resp.text
                    # Post bloklarini topamiz
                    # data-post="channel/12345"
                    posts = re.findall(
                        r'data-post="([^"]+)".*?tgme_widget_message_text[^>]*>(.*?)</div>',
                        html,
                        re.DOTALL,
                    )

                    for post_id, text_html in posts[-10:]:  # Eng so'nggi 10 ta post
                        clean_text = re.sub(r"<[^>]+>", " ", text_html).strip()
                        # Agar post ish/xodim e'loni bo'lsa (masalan "Xodim kerak", "Ish joyi", "Vakansiya", "#ish")
                        if any(kw in clean_text.lower() for kw in ["xodim", "vakansiya", "ish", "developer", "dasturchi"]):
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

                            first_line = clean_text.split("\n")[0][:100]

                            all_posts.append({
                                "id": post_id,
                                "channel": ch,
                                "url": f"https://t.me/{post_id}",
                                "title": first_line or f"E'lon ({ch})",
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
        return {
            "source": self.source_name,
            "external_id": str(raw.get("id")),
            "title": raw.get("title", "Telegram Vakansiya"),
            "company": f"Telegram: @{raw.get('channel', 'kanal')}",
            "city": "O'zbekiston",
            "salary_min": None,
            "salary_max": None,
            "currency": None,
            "description": raw.get("description", ""),
            "url": raw.get("url", ""),
            "contact_phone": raw.get("phone"),
            "contact_telegram": raw.get("telegram"),
            "contact_email": None,
            "raw_data": json.dumps(raw, ensure_ascii=False),
            "published_at": datetime.now(UTC),
        }
