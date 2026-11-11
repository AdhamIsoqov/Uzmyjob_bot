"""Vakansiya qidirish, normallashtirish, deduplikatsiya, saralash va xabarnoma pipeline'i."""
import asyncio
import json
import re
from datetime import UTC, datetime, timedelta, timezone
from html import escape
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import or_, select

from uzmyjob.adapters.base import ScraperAdapter
from uzmyjob.adapters.hh_api import HeadHunterAdapter
from uzmyjob.adapters.jobs_uz import JobsUzScraperAdapter
from uzmyjob.adapters.osonish import OsonIshAdapter
from uzmyjob.adapters.rss import RSSFreelanceAdapter
from uzmyjob.adapters.tg_channels import TelegramChannelAdapter
from uzmyjob.agents.matcher import compute_l1_score, match_vacancy
from uzmyjob.models.base import AsyncSessionLocal
from uzmyjob.models.user import User
from uzmyjob.models.vacancy import Vacancy
from uzmyjob.pipeline.dead_letter import SourceHealthTracker
from uzmyjob.utils.filters import is_blacklisted, is_candidate_resume
from uzmyjob.utils.logger import log
from uzmyjob.utils.metrics import (
    DEDUPLICATED_TOTAL,
    VACANCIES_FETCHED,
    update_system_gauges,
)


def normalize_text_for_dedupe(text: str | None) -> str:
    """Sarlavha yoki kompaniya nomini solishtirish uchun tozalash."""
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    stopwords = {"mchj", "llc", "ooo", "inc", "co", "ltd", "aj", "kompaniyasi", "company"}
    words = [w for w in cleaned.split() if w not in stopwords]
    return " ".join(words)


def format_published_date(dt: datetime | None) -> str:
    """E'lon sanasi va vaqtini Telegram uchun qulay formatlash (O'zbekiston vaqti)."""
    if not dt:
        return "Yaqinda e'lon qilingan"

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
                InlineKeyboardButton(text="✅ Murojaat qilish", callback_data=f"apply:{vacancy_id}"),
                InlineKeyboardButton(text="✉️ Xabar tayyorlash", callback_data=f"cover:{vacancy_id}"),
            ],
            [
                InlineKeyboardButton(text="🔖 Saqlash", callback_data=f"save:{vacancy_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"dismiss:{vacancy_id}"),
            ],
        ]
    )


def _truncate_str(value: str | None, max_len: int) -> str | None:
    if value is None:
        return None
    return value[:max_len]


def _sanitize_vacancy_data(raw: dict[str, Any]) -> dict[str, Any]:
    """DB ustunlari chegarasiga moslashtirilgan vakansiya ma'lumotlari."""
    data = dict(raw)
    data["source"] = (_truncate_str(str(data.get("source") or "unknown"), 50)) or "unknown"
    data["external_id"] = (_truncate_str(str(data.get("external_id") or ""), 200)) or ""
    data["title"] = (_truncate_str(str(data.get("title") or "Vakansiya"), 300)) or "Vakansiya"
    data["company"] = _truncate_str(data.get("company"), 200)
    data["city"] = _truncate_str(data.get("city"), 100)
    data["currency"] = _truncate_str(data.get("currency"), 10)
    data["url"] = (_truncate_str(str(data.get("url") or ""), 500)) or ""
    data["contact_phone"] = _truncate_str(data.get("contact_phone"), 50)
    data["contact_telegram"] = _truncate_str(data.get("contact_telegram"), 100)
    data["contact_email"] = _truncate_str(data.get("contact_email"), 200)
    return data


def _build_user_profile(user: User) -> dict[str, Any]:
    """User ORM obyektidan matcher uchun lug'at yaratish."""
    return {
        "telegram_id": user.telegram_id,
        "match_threshold": user.match_threshold,
        "position": user.position or "",
        "city": user.city or "",
        "experience_years": user.experience_years or 0,
        "min_salary": user.min_salary or 0,
        "employment_type": user.employment_type or "",
        "keywords": json.loads(user.keywords) if user.keywords else [],
        "blacklist": json.loads(user.blacklist) if user.blacklist else [],
    }


def _vacancy_to_dict(vac: Vacancy) -> dict[str, Any]:
    """Vacancy ORM obyektidan matcher/formatlash uchun mustaqil lug'at yaratish."""
    return {
        "id": vac.id,
        "source": vac.source,
        "external_id": vac.external_id,
        "title": vac.title,
        "company": vac.company,
        "city": vac.city,
        "salary_min": vac.salary_min,
        "salary_max": vac.salary_max,
        "currency": vac.currency,
        "description": vac.description,
        "url": vac.url,
        "published_at": vac.published_at,
    }


class JobPipeline:
    """Manbalardan vakansiyalarni olib, qayta ishlovchi va foydalanuvchiga yetkazuvchi pipeline."""

    def __init__(self, bot: Bot | None = None, adapters: list[ScraperAdapter] | None = None) -> None:
        self.bot = bot
        self.adapters = adapters or [
            HeadHunterAdapter(),
            OsonIshAdapter(),
            JobsUzScraperAdapter(),
            TelegramChannelAdapter(),
            RSSFreelanceAdapter(),
        ]

    def _is_blacklisted(self, title: str, description: str | None, blacklist: list[str]) -> bool:
        return is_blacklisted(title, description, blacklist)

    async def run_once(self) -> dict[str, int]:
        """Bir siklni bajarish: fetch -> dedupe/save -> match/notify -> metrics."""
        stats = {"fetched": 0, "new_saved": 0, "notified": 0}
        all_vacancies: list[dict[str, Any]] = []

        for adapter in self.adapters:
            if getattr(adapter, "is_stub", False):
                continue
            try:
                raw_items = await adapter.fetch()
                stats["fetched"] += len(raw_items)
                for item in raw_items:
                    all_vacancies.append(_sanitize_vacancy_data(adapter.normalize(item)))
                await SourceHealthTracker.record_success(adapter.source_name)
            except Exception as exc:
                log.error("adapter_run_error", source=adapter.source_name, error=str(exc))
                await SourceHealthTracker.record_failure(adapter.source_name, str(exc))

        saved_vacancies = await self._save_new_vacancies(all_vacancies)
        stats["new_saved"] = len(saved_vacancies)
        log.info("pipeline_vacancies_saved", count=len(saved_vacancies))

        if self.bot and saved_vacancies:
            stats["notified"] = await self._match_and_notify_users(saved_vacancies)

        await update_system_gauges()
        return stats

    async def _save_new_vacancies(self, vacancies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Vakansiyalarni bazaga saqlash va xotiraga bog'lanmagan dict ro'yxatini qaytarish."""
        if not vacancies:
            return []

        saved_dicts: list[dict[str, Any]] = []
        async with AsyncSessionLocal() as session:
            recent_stmt = select(Vacancy.title, Vacancy.company).order_by(Vacancy.id.desc()).limit(300)
            recent_rows = (await session.execute(recent_stmt)).all()
            seen_signatures = {
                f"{normalize_text_for_dedupe(r[0])}|{normalize_text_for_dedupe(r[1])}"
                for r in recent_rows
                if r[0]
            }

            existing_keys_stmt = select(Vacancy.source, Vacancy.external_id).order_by(Vacancy.id.desc()).limit(1000)
            existing_pairs = {(r[0], r[1]) for r in (await session.execute(existing_keys_stmt)).all()}

            for raw_item in vacancies:
                v_data = _sanitize_vacancy_data(raw_item)
                source = v_data["source"]
                ext_id = v_data["external_id"]

                if (source, ext_id) in existing_pairs:
                    DEDUPLICATED_TOTAL.labels(reason="source_id").inc()
                    continue

                stmt = select(Vacancy.id).where(Vacancy.source == source, Vacancy.external_id == ext_id)
                if (await session.execute(stmt)).scalar_one_or_none():
                    existing_pairs.add((source, ext_id))
                    DEDUPLICATED_TOTAL.labels(reason="source_id").inc()
                    continue

                title = v_data["title"]
                comp = v_data.get("company") or ""
                norm_sig = f"{normalize_text_for_dedupe(title)}|{normalize_text_for_dedupe(comp)}"
                if norm_sig in seen_signatures and len(norm_sig) > 6:
                    DEDUPLICATED_TOTAL.labels(reason="content_hash").inc()
                    log.info("cross_source_duplicate_skipped", title=title, company=comp, source=source)
                    continue

                existing_pairs.add((source, ext_id))
                seen_signatures.add(norm_sig)

                new_vacancy = Vacancy(**v_data)
                session.add(new_vacancy)
                await session.flush()
                saved_dicts.append(_vacancy_to_dict(new_vacancy))
                VACANCIES_FETCHED.labels(source=source).inc()

            await session.commit()

        return saved_dicts

    async def _match_and_notify_users(self, vacancies: list[dict[str, Any]]) -> int:
        """Faol foydalanuvchilarga mos yangi vakansiyalarni yuborish (DB session ochiq ushlanmaydi)."""
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.is_active.is_(True), User.position.isnot(None))
            users = (await session.execute(stmt)).scalars().all()
            user_profiles = [_build_user_profile(u) for u in users]

        notified = 0
        for profile in user_profiles:
            for vac_dict in vacancies:
                if is_candidate_resume(vac_dict["title"], vac_dict.get("description")):
                    continue
                if is_blacklisted(vac_dict["title"], vac_dict.get("description"), profile["blacklist"]):
                    continue

                score, reason = await match_vacancy(profile, vac_dict)
                if score >= profile["match_threshold"]:
                    if await self._send_vacancy_to_user(profile["telegram_id"], vac_dict, score, reason):
                        notified += 1

        return notified

    async def _send_vacancy_to_user(
        self,
        telegram_id: int,
        vacancy: dict[str, Any],
        score: float,
        reason: str,
    ) -> bool:
        """Telegram orqali foydalanuvchiga HTML-xavfsiz vakansiya kartochkasini yuboradi."""
        if not self.bot:
            return False

        salary_str = "Ko'rsatilmagan"
        s_min_val = vacancy.get("salary_min")
        s_max_val = vacancy.get("salary_max")
        if s_min_val or s_max_val:
            s_min = f"{s_min_val:,}" if s_min_val else ""
            s_max = f"{s_max_val:,}" if s_max_val else ""
            curr = escape(str(vacancy.get("currency") or ""))
            if s_min and s_max:
                salary_str = f"{s_min} - {s_max} {curr}".strip()
            elif s_min:
                salary_str = f"dan {s_min} {curr}".strip()
            else:
                salary_str = f"gacha {s_max} {curr}".strip()

        pct = int(score * 100)
        source_icons = {
            "hh": "🔴 [hh.uz]",
            "olx": "🟢 [OLX.uz]",
            "jobs_uz": "🔵 [jobs.uz]",
            "tg_channel": "✈️ [Telegram]",
            "freelance_rss": "🌐 [Freelance]",
        }
        source_label = source_icons.get(vacancy["source"], f"[{escape(vacancy['source'])}]")
        date_str = format_published_date(vacancy.get("published_at"))

        title_safe = escape(vacancy.get("title") or "Vakansiya")
        company_safe = escape(vacancy.get("company") or "Nomaʼlum")
        city_safe = escape(vacancy.get("city") or "Nomaʼlum")
        reason_safe = escape(reason or "")
        url_safe = escape(vacancy.get("url") or "", quote=True)

        text = (
            f"{source_label} <b>{title_safe}</b>\n\n"
            f"🏢 <b>Kompaniya:</b> {company_safe}\n"
            f"📍 <b>Hudud:</b> {city_safe}\n"
            f"💰 <b>Maosh:</b> <b>{salary_str}</b>\n"
            f"📅 <b>E'lon vaqti:</b> {date_str}\n"
            f"🎯 <b>Moslik darajasi:</b> <b>{pct}%</b> (✅)\n\n"
            f"<blockquote>💡 <b>Tahlil:</b> {reason_safe}</blockquote>\n\n"
            f"🔗 <a href='{url_safe}'><b>Asl e'lonni ochish ↗</b></a>"
        )

        for attempt in range(2):
            try:
                await self.bot.send_message(
                    chat_id=telegram_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=build_vacancy_keyboard(vacancy["id"]),
                    disable_web_page_preview=False,
                )
                await asyncio.sleep(0.05)
                return True
            except TelegramRetryAfter as exc:
                if attempt == 0:
                    await asyncio.sleep(exc.retry_after + 0.5)
                    continue
                log.warning("send_vacancy_rate_limited", telegram_id=telegram_id)
                return False
            except Exception as exc:
                log.error("send_vacancy_failed", telegram_id=telegram_id, error=str(exc))
                return False
        return False

    async def backfill_for_user(self, user_telegram_id: int, limit: int = 5) -> int:
        """Foydalanuvchiga so'nggi 7 kunlik eng mos vakansiyalarni yuborish."""
        seven_days_ago = datetime.now(UTC) - timedelta(days=7)

        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.telegram_id == user_telegram_id, User.is_active.is_(True))
            user = (await session.execute(stmt)).scalar_one_or_none()
            if not user or not user.position:
                return 0
            profile = _build_user_profile(user)

            vac_stmt = (
                select(Vacancy)
                .where(
                    or_(
                        Vacancy.published_at >= seven_days_ago,
                        Vacancy.fetched_at >= seven_days_ago,
                    )
                )
                .order_by(Vacancy.id.desc())
                .limit(50)
            )
            vac_dicts = [_vacancy_to_dict(v) for v in (await session.execute(vac_stmt)).scalars().all()]

        # Avval tezkor L1 skoring bilan eng yaxshi nomzodlarni saralab olamiz (LLM portlashini oldini olish)
        l1_candidates: list[tuple[float, dict[str, Any]]] = []
        for vac_dict in vac_dicts:
            if is_candidate_resume(vac_dict["title"], vac_dict.get("description")):
                continue
            if is_blacklisted(vac_dict["title"], vac_dict.get("description"), profile["blacklist"]):
                continue
            l1_score, _ = compute_l1_score(profile, vac_dict)
            if l1_score >= 0.20:
                l1_candidates.append((l1_score, vac_dict))

        l1_candidates.sort(key=lambda x: x[0], reverse=True)
        top_candidates = [v for _, v in l1_candidates[:10]]

        matches: list[tuple[dict[str, Any], float, str]] = []
        all_scored: list[tuple[dict[str, Any], float, str]] = []
        for vac_dict in top_candidates:
            score, reason = await match_vacancy(profile, vac_dict)
            all_scored.append((vac_dict, score, reason))
            if score >= profile["match_threshold"]:
                matches.append((vac_dict, score, reason))

        matches.sort(key=lambda x: x[1], reverse=True)
        sent_count = 0
        if matches:
            for vac_dict, score, reason in matches[:limit]:
                if await self._send_vacancy_to_user(profile["telegram_id"], vac_dict, score, reason):
                    sent_count += 1
            return sent_count

        fallback_candidates = sorted(
            [x for x in all_scored if x[1] >= 0.25],
            key=lambda x: x[1],
            reverse=True,
        )[:limit]
        if fallback_candidates and self.bot:
            await self.bot.send_message(
                chat_id=profile["telegram_id"],
                text=(
                    f"ℹ️ Belgilangan <b>{int(profile['match_threshold'] * 100)}%</b> moslikka to'liq yetmagan bo'lsa-da, "
                    "bazadagi eng yaqin va so'nggi takliflar:"
                ),
                parse_mode="HTML",
            )
            for vac_dict, score, reason in fallback_candidates:
                if await self._send_vacancy_to_user(
                    profile["telegram_id"], vac_dict, score, f"{reason} (Tavsiya)"
                ):
                    sent_count += 1

        return sent_count
