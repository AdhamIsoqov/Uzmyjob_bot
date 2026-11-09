"""Vakansiya qidirish, normallashtirish, deduplikatsiya, saralash va xabarnoma pipeline'i."""
import asyncio
import json
import re
from datetime import UTC, datetime, timedelta, timezone
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
from uzmyjob.utils.metrics import (
    DEDUPLICATED_TOTAL,
    SOURCE_ERRORS_TOTAL,
    VACANCIES_FETCHED,
    update_system_gauges,
)


def normalize_text_for_dedupe(text: str | None) -> str:
    """Sarlavha yoki kompaniya nomini solishtirish uchun tozalash."""
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    stopwords = ["mchj", "llc", "ooo", "inc", "co", "ltd", "aj", "kompaniyasi", "company"]
    words = [w for w in cleaned.split() if w not in stopwords]
    return " ".join(words)


def format_published_date(dt: datetime | None) -> str:
    """E'lon sanasi va vaqtini Telegram uchun qulay formatlash (O'zbekiston vaqti)."""
    if not dt:
        return "Yaqinda e'lon qilingan"

    # Agar timezone yo'q bo'lsa UTC deb olamiz
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    uz_tz = timezone(timedelta(hours=5))
    local_dt = dt.astimezone(uz_tz)
    now_local = datetime.now(uz_tz)

    time_str = local_dt.strftime("%H:%M")
    diff = now_local - local_dt

    if diff.total_seconds() < 3600:
        mins = max(1, int(diff.total_seconds() / 60))
        return f"Bugun, {time_str} ({mins} daqiqa oldin)"
    if local_dt.date() == now_local.date():
        hours = int(diff.total_seconds() / 3600)
        return f"Bugun, {time_str} ({hours} soat oldin)"
    if local_dt.date() == (now_local - timedelta(days=1)).date():
        return f"Kecha, {time_str}"
    return local_dt.strftime("%d.%m.%Y, %H:%M")


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

        # 4. Dinamik monitoring metrikalarini yangilash
        await update_system_gauges()

        return stats

    async def _update_source_status(self, source_name: str, status: str, error: str | None = None):
        """Manba holatini va xatolarini Source jadvalida qayd etish (Dead-letter tracking)."""
        if status == "error":
            SOURCE_ERRORS_TOTAL.labels(source=source_name).inc()

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
        Vakansiyalarni bazaga saqlash.
        1. (source, external_id) unikal tekshiruv.
        2. Cross-source content deduplikatsiya (sarlavha + kompaniya).
        """
        if not vacancies:
            return []

        saved: list[Vacancy] = []
        async with AsyncSessionLocal() as session:
            # So'nggi 200 ta vakansiyaning sarlavha va kompaniya imzolarini olamiz
            recent_stmt = (
                select(Vacancy.title, Vacancy.company)
                .order_by(Vacancy.id.desc())
                .limit(200)
            )
            recent_rows = (await session.execute(recent_stmt)).all()
            seen_signatures = {
                f"{normalize_text_for_dedupe(r[0])}|{normalize_text_for_dedupe(r[1])}"
                for r in recent_rows
                if r[0]
            }

            for v_data in vacancies:
                source = v_data.get("source", "unknown")
                ext_id = v_data.get("external_id", "")

                # 1. Manba bo'yicha unikal tekshiruv
                stmt = select(Vacancy).where(
                    Vacancy.source == source,
                    Vacancy.external_id == ext_id,
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing:
                    DEDUPLICATED_TOTAL.labels(reason="source_id").inc()
                    continue

                # 2. Cross-source dublikat tekshiruvi
                title = v_data.get("title", "")
                comp = v_data.get("company", "")
                norm_sig = f"{normalize_text_for_dedupe(title)}|{normalize_text_for_dedupe(comp)}"
                if norm_sig in seen_signatures and len(norm_sig) > 6:
                    DEDUPLICATED_TOTAL.labels(reason="content_hash").inc()
                    log.info("cross_source_duplicate_skipped", title=title, company=comp, source=source)
                    continue

                seen_signatures.add(norm_sig)
                new_vacancy = Vacancy(**v_data)
                session.add(new_vacancy)
                await session.flush()
                saved.append(new_vacancy)
                VACANCIES_FETCHED.labels(source=source).inc()

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

                    # Nomzod rezyumesi va Blacklist tekshiruvi (tezkor L1 filtr)
                    if self._is_candidate_resume(vac.title, vac.description):
                        continue
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

    def _is_candidate_resume(self, title: str, description: str | None) -> bool:
        """Nomzod rezyumesi yoki noprofil e'lonlarni aniqlash."""
        full = f"{title} {description or ''}".lower()
        candidate_markers = [
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
            "burger king",
            "добро пожаловать в канал",
            "bo'sh ish o'rinlarini ochish",
        ]
        if any(marker in full for marker in candidate_markers):
            return True
        return bool(re.search(r"\bxodim:\s*[a-zа-яa-z]", full) or "kasbi:" in full)

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
        date_str = format_published_date(vacancy.published_at)

        text = (
            f"{source_label} <b>{vacancy.title}</b>\n\n"
            f"🏢 <b>Kompaniya:</b> {vacancy.company or 'Nomaʼlum'}\n"
            f"📍 <b>Hudud:</b> {vacancy.city or 'Nomaʼlum'}\n"
            f"💰 <b>Maosh:</b> <b>{salary_str}</b>\n"
            f"📅 <b>E'lon vaqti:</b> {date_str}\n"
            f"🎯 <b>Moslik darajasi:</b> <b>{pct}%</b> (✅)\n\n"
            f"<blockquote>💡 <b>Tahlil:</b> {reason}</blockquote>\n\n"
            f"🔗 <a href='{vacancy.url}'><b>Telegramdagi asl postni ochish ↗</b></a>"
        )

        try:
            await self.bot.send_message(
                chat_id=user.telegram_id,
                text=text,
                parse_mode="HTML",
                reply_markup=build_vacancy_keyboard(vacancy.id),
                disable_web_page_preview=False,
            )
            # Anti-flood sleep
            await asyncio.sleep(0.05)
            return True
        except Exception as e:
            log.error("send_vacancy_failed", telegram_id=user.telegram_id, error=str(e))
            return False

    async def backfill_for_user(self, user_telegram_id: int, limit: int = 5) -> int:
        """
        Yangi ro'yxatdan o'tgan foydalanuvchiga so'nggi 7 kunlik mos vakansiyalarni yuborish (Backfill).
        """
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.telegram_id == user_telegram_id, User.is_active == True)
            user = (await session.execute(stmt)).scalar_one_or_none()
            if not user or not user.position:
                return 0

            user_profile = {
                "position": user.position or "",
                "city": user.city or "",
                "experience_years": user.experience_years or 0,
                "min_salary": user.min_salary or 0,
                "employment_type": user.employment_type or "",
                "keywords": json.loads(user.keywords) if user.keywords else [],
                "blacklist": json.loads(user.blacklist) if user.blacklist else [],
            }

            vac_stmt = (
                select(Vacancy)
                .order_by(Vacancy.id.desc())
                .limit(30)
            )
            vacancies = (await session.execute(vac_stmt)).scalars().all()

            matches = []
            all_scored = []
            for vac in vacancies:
                if self._is_candidate_resume(vac.title, vac.description):
                    continue
                if self._is_blacklisted(vac.title, vac.description, user_profile["blacklist"]):
                    continue

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
                score, reason = await match_vacancy(user_profile, vac_dict)
                all_scored.append((vac, score, reason))
                if score >= user.match_threshold:
                    matches.append((vac, score, reason))

            # 1. Agar threshold bo'yicha mos vakansiyalar bo'lsa
            matches.sort(key=lambda x: x[1], reverse=True)
            sent_count = 0
            if matches:
                for vac, score, reason in matches[:limit]:
                    sent = await self._send_vacancy_to_user(user, vac, score, reason)
                    if sent:
                        sent_count += 1
                return sent_count

            # 2. Agar threshold bo'yicha 0 ta bo'lsa, bazadagi eng yaqin / so'nggi takliflarni taqdim etamiz (kamida 25% moslik)
            all_scored = [x for x in all_scored if x[1] >= 0.25]
            all_scored.sort(key=lambda x: x[1], reverse=True)
            fallback_candidates = all_scored[:limit]
            if fallback_candidates and self.bot:
                await self.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"ℹ️ Belgilangan <b>{int(user.match_threshold * 100)}%</b> moslikka to'liq yetmagan bo'lsa-da, "
                         f"bazadagi eng yaqin va so'nggi takliflar:",
                    parse_mode="HTML",
                )
                for vac, score, reason in fallback_candidates:
                    sent = await self._send_vacancy_to_user(user, vac, score, f"{reason} (Tavsiya)")
                    if sent:
                        sent_count += 1

            return sent_count
