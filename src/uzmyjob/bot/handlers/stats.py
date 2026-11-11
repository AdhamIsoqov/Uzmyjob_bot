"""Statistika va CSV export handlerlari (/statistika, /export)."""

import csv
import io
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import func, select

from uzmyjob.models.application import Application
from uzmyjob.models.base import AsyncSessionLocal
from uzmyjob.models.user import User
from uzmyjob.models.vacancy import Vacancy

router = Router()

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _sanitize_csv_cell(value: object) -> str:
    """CSV/Excel formula injection (DDE) hujumidan himoya."""
    text = "" if value is None else str(value)
    if text and text[0] in _FORMULA_PREFIXES:
        return "'" + text
    return text


async def _build_stats_text(telegram_id: int) -> str | None:
    """Foydalanuvchi statistikasi HTML matnini tuzish."""
    async with AsyncSessionLocal() as session:
        u_stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(u_stmt)).scalar_one_or_none()
        if not user:
            return None

        app_stmt = (
            select(func.count())
            .select_from(Application)
            .where(Application.user_id == user.id)
        )
        total_applied = (await session.execute(app_stmt)).scalar() or 0

        vac_stmt = select(func.count()).select_from(Vacancy)
        total_vacancies = (await session.execute(vac_stmt)).scalar() or 0

        position_safe = escape(user.position or "Belgilanmagan")
        city_safe = escape(user.city or "Belgilanmagan")

        return (
            "📊 <b>Sizning murojaatlar statistikangiz:</b>\n\n"
            f"🎯 Tanlangan lavozim: <b>{position_safe}</b>\n"
            f"📍 Shahar: <b>{city_safe}</b>\n"
            f"📨 Yuborilgan arizalar: <b>{total_applied} ta</b>\n"
            f"🗂 Bazadagi jami vakansiyalar: <b>{total_vacancies} ta</b>\n\n"
            "📥 Murojaatlar tarixini yuklab olish uchun: /export"
        )


@router.message(Command("statistika"))
@router.message(Command("stats"))
@router.message(F.text == "📊 Statistika")
async def cmd_statistika(message: Message):
    """Foydalanuvchining umumiy murojaatlar statistikasini ko'rsatish."""
    if not message.from_user:
        return
    text = await _build_stats_text(message.from_user.id)
    if not text:
        await message.answer("⚠️ Avval /start yoki /profil orqali ro'yxatdan o'ting.")
        return
    await message.answer(text)


@router.callback_query(F.data == "open_stats")
async def process_open_stats_callback(callback: CallbackQuery):
    """Callback orqali statistikani ko'rish."""
    text = await _build_stats_text(callback.from_user.id)
    if not text:
        await callback.answer("Foydalanuvchi topilmadi")
        return
    await callback.answer()
    if callback.message:
        await callback.message.answer(text)


@router.message(Command("export"))
async def cmd_export(message: Message):
    """Murojaatlar tarixini CSV fayl ko'rinishida yuborish."""
    if not message.from_user:
        return
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        u_stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(u_stmt)).scalar_one_or_none()

        if not user:
            await message.answer("Foydalanuvchi topilmadi.")
            return

        stmt = (
            select(Application, Vacancy)
            .join(Vacancy, Application.vacancy_id == Vacancy.id, isouter=True)
            .where(Application.user_id == user.id)
            .order_by(Application.applied_at.desc())
        )
        rows = (await session.execute(stmt)).all()

    if not rows:
        await message.answer("Hozircha yuborilgan murojaatlar mavjud emas.")
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Manba", "Vakansiya", "Kompaniya", "Holati", "Sana", "Havola"])

    for app, vac in rows:
        writer.writerow([
            app.id,
            _sanitize_csv_cell(app.source),
            _sanitize_csv_cell(vac.title if vac else "Nomaʼlum"),
            _sanitize_csv_cell(vac.company if vac else ""),
            _sanitize_csv_cell(app.status.value if hasattr(app.status, "value") else str(app.status)),
            app.applied_at.strftime("%Y-%m-%d %H:%M") if app.applied_at else "",
            _sanitize_csv_cell(vac.url if vac else ""),
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    doc_file = BufferedInputFile(csv_bytes, filename="murojaatlar_tarixi.csv")

    await message.answer_document(
        document=doc_file,
        caption="📁 <b>Barcha murojaatlaringiz tarixi (CSV)</b>",
    )
