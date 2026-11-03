"""Vakansiya qidirish, normallashtirish, deduplikatsiya, saralash va xabarnoma pipeline'i."""
import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from uzmyjob.adapters.base import ScraperAdapter
from uzmyjob.adapters.hh_api import HeadHunterAdapter
from uzmyjob.adapters.jobs_uz import JobsUzScraperAdapter
from uzmyjob.adapters.olx import OLXScraperAdapter
from uzmyjob.adapters.tg_channels import TelegramChannelAdapter
from uzmyjob.agents.matcher import match_vacancy
from uzmyjob.models.base import AsyncSessionLocal
from uzmyjob.models.source import Source
from uzmyjob.models.user import User
from uzmyjob.models.vacancy import Vacancy
from uzmyjob.utils.logger import log


def build_vacancy_keyboard(vacancy_id: int) -> InlineKeyboardMarkup:
    """Vakansiya xabari ostidagi interaktiv inline tugmalar."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Murojaat qilish",
                    callback_data=f"apply:{vacancy_id}",
                ),
                InlineKeyboardButton(
                    text="✉️ Xabar tayyorlash",
                    callback_data=f"cover:{vacancy_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔖 Saqlash",
                    callback_data=f"save:{vacancy_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Rad etish",
                    callback_data=f"dismiss:{vacancy_id}",
                ),
            ],
        ]
    )


class JobPipeline:
    """Manbalardan vakansiyalarni olib, qayta ishlovchi va foydalanuvchiga yetkazuvchi asosiy pipeline."""

    def __init__(self, bot: Bot | None = None, adapters: list[ScraperAdapter] | None = None):
        self.bot = bot
        self.adapters = adapters or [
            HeadHunterAdapter(),
            OLXScraperAdapter(),
            JobsUzScraperAdapter(),
            TelegramChannelAdapter(),
        ]

    async def run_once(self) -> dict[str, int]:
        """
        Bir siklni to'liq bajarish:
        1. Har bir adapterdan vakansiyalarni olish.
        2. Deduplikatsiya va DB'ga yangilarini yozish.
        3. Faol foydalanuvchilarga moslarini saralash va yuborish.
        """
        stats = {"fetched": 0, "new_saved": 0, "notified": 0}

        # 1. Fetch & Normalize
        all_vacancies: list[dict[str, Any]] = []
        for adapter in self.adapters:
            try:
                raw_items = await adapter.fetch()
                stats["fetched"] += len(raw_items)
                for item in raw_items:
                    norm = adapter.normalize(item)
                    all_vacancies.append(norm)
                await self._update_source_status(adapter.source_name, status="ok")
            except Exception as e:
                log.error("adapter_run_error", source=adapter.source_name, error=str(e))
                await self._update_source_status(adapter.source_name, status="error", error=str(e))

        # 2. Dedupe & Save into DB
        saved_vacancies = await self._save_new_vacancies(all_vacancies)
        stats["new_saved"] = len(saved_vacancies)
        log.info("pipeline_vacancies_saved", count=len(saved_vacancies))

        # 3. Match & Notify
        if self.bot and saved_vacancies:
            notified_count = await self._match_and_notify_users(saved_vacancies)
            stats["notified"] = notified_count

        return stats

    async def _update_source_status(self, source_name: str, status: str, error: str | None = None):
        """Manba holatini va xatolarini Source jadvalida qayd etish (Dead-letter tracking)."""
        async with AsyncSessionLocal() as session:
            stmt = select(Source).where(Source.name == source_name)
            src_obj = (await session.execute(stmt)).scalar_one_or_none()

            if not src_obj:
                src_obj = Source(name=source_name)
                session.add(src_obj)

            src_obj.status = status
            src_obj.last_checked_at = datetime.now(UTC)
            if status == "error":
                src_obj.error_count += 1
                src_obj.last_error = error
            else:
                src_obj.error_count = 0

            await session.commit()

    async def _save_new_vacancies(self, vacancies: list[dict[str, Any]]) -> list[Vacancy]:
        """
        Vakansiyalarni bazaga saqlash. Agar (source, external_id) mavjud bo'lsa, o'tkazib yuboriladi.
        """
        if not vacancies:
            return []

        saved: list[Vacancy] = []
        async with AsyncSessionLocal() as session:
            for v_data in vacancies:
                stmt = select(Vacancy).where(
                    Vacancy.source == v_data["source"],
                    Vacancy.external_id == v_data["external_id"],
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing:
                    continue

                new_vacancy = Vacancy(**v_data)
                session.add(new_vacancy)
                await session.flush()
                saved.append(new_vacancy)

            await session.commit()

        return saved

    async def _match_and_notify_users(self, vacancies: list[Vacancy]) -> int:
        """
        Faol foydalanuvchilarni olib, yangi vakansiyalarga match qilish va Telegramga yuborish.
        """
        notified = 0
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.is_active == True)
            users = (await session.execute(stmt)).scalars().all()

            for user in users:
                user_profile = {
                    "position": user.position or "",
                    "city": user.city or "",
                    "experience_years": user.experience_years or 0,
                    "min_salary": user.min_salary or 0,
                    "employment_type": user.employment_type or "",
                    "keywords": json.loads(user.keywords) if user.keywords else [],
                    "blacklist": json.loads(user.blacklist) if user.blacklist else [],
                }

                for vac in vacancies:
                    vac_dict = {
                        "external_id": vac.external_id,
                        "title": vac.title,
                        "company": vac.company,
                        "city": vac.city,
                        "salary_min": vac.salary_min,
                        "salary_max": vac.salary_max,
                        "currency": vac.currency,
                        "description": vac.description,
                    }

                    # Blacklist tekshiruvi (tezkor L1 filtr)
                    if self._is_blacklisted(vac.title, vac.description, user_profile["blacklist"]):
                        continue

                    # Gemini agent orqali moslikni baholash
                    score, reason = await match_vacancy(user_profile, vac_dict)

                    if score >= user.match_threshold:
                        sent = await self._send_vacancy_to_user(user, vac, score, reason)
                        if sent:
                            notified += 1

        return notified

    def _is_blacklisted(self, title: str, description: str | None, blacklist: list[str]) -> bool:
        """Sarlavha yoki tavsifda taqiqlangan so'zlar borligini tekshiradi."""
        text = f"{title} {description or ''}".lower()
        for word in blacklist:
            if word and word.strip().lower() in text:
                return True
        return False

    async def _send_vacancy_to_user(
        self, user: User, vacancy: Vacancy, score: float, reason: str
    ) -> bool:
        """Telegram orqali foydalanuvchiga vakansiya kartochkasini yuboradi."""
        if not self.bot:
            return False

        salary_str = "Ko'rsatilmagan"
        if vacancy.salary_min or vacancy.salary_max:
            s_min = f"{vacancy.salary_min:,}" if vacancy.salary_min else ""
            s_max = f"{vacancy.salary_max:,}" if vacancy.salary_max else ""
            curr = vacancy.currency or ""
            if s_min and s_max:
                salary_str = f"{s_min} - {s_max} {curr}"
            elif s_min:
                salary_str = f"dan {s_min} {curr}"
            else:
                salary_str = f"gacha {s_max} {curr}"

        pct = int(score * 100)
        source_icons = {
            "hh": "🔴 [hh.uz]",
            "olx": "🟢 [OLX.uz]",
            "jobs_uz": "🔵 [jobs.uz]",
            "tg_channel": "✈️ [Telegram]",
        }
        source_label = source_icons.get(vacancy.source, f"[{vacancy.source}]")

        text = (
            f"{source_label} <b>{vacancy.title}</b>\n"
            f"🏢 Kompaniya: <b>{vacancy.company or 'Nomaʼlum'}</b>\n"
            f"📍 Manzil: {vacancy.city or 'Nomaʼlum'}\n"
            f"💰 Maosh: <b>{salary_str}</b>\n"
            f"🎯 Moslik darajasi: <b>{pct}%</b> (✅)\n"
            f"💡 <i>{reason}</i>\n\n"
            f"🔗 <a href='{vacancy.url}'>Vakansiya havolasi</a>"
        )

        try:
            await self.bot.send_message(
                chat_id=user.telegram_id,
                text=text,
                reply_markup=build_vacancy_keyboard(vacancy.id),
                disable_web_page_preview=False,
            )
            # Anti-flood sleep
            await asyncio.sleep(0.05)
            return True
        except Exception as e:
            log.error("send_vacancy_failed", telegram_id=user.telegram_id, error=str(e))
            return False
