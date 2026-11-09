"""Statistika va CSV export handlerlari (/statistika, /export)."""
import csv
import io

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import func, select

from uzmyjob.models.application import Application
from uzmyjob.models.base import AsyncSessionLocal
from uzmyjob.models.user import User
from uzmyjob.models.vacancy import Vacancy

router = Router()


@router.message(Command("statistika"))
@router.message(Command("stats"))
@router.message(F.text == "📊 Statistika")
async def cmd_statistika(message: Message):
    """Foydalanuvchining bugungi va umumiy murojaatlar statistikasini ko'rsatish."""
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        u_stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(u_stmt)).scalar_one_or_none()

        if not user:
            await message.answer("⚠️ Avval /start yoki /profil orqali ro'yxatdan o'ting.")
            return

        # Jami yuborilgan arizalar
        app_stmt = select(func.count()).select_from(Application).where(Application.user_id == user.id)
        total_applied = (await session.execute(app_stmt)).scalar() or 0

        # Jami bazadagi vakansiyalar
        vac_stmt = select(func.count()).select_from(Vacancy)
        total_vacancies = (await session.execute(vac_stmt)).scalar() or 0

        text = (
            "📊 <b>Sizning murojaatlar statistikangiz:</b>\n\n"
            f"🎯 Tanlangan lavozim: <b>{user.position or 'Belgilanmagan'}</b>\n"
            f"📍 Shahar: <b>{user.city or 'Belgilanmagan'}</b>\n"
            f"📨 Yuborilgan arizalar: <b>{total_applied} ta</b>\n"
            f"🗂 Bazadagi jami vakansiyalar: <b>{total_vacancies} ta</b>\n\n"
            "📥 Murojaatlar tarixini yuklab olish uchun: /export"
        )
        await message.answer(text)


@router.callback_query(F.data == "open_stats")
async def process_open_stats_callback(callback: CallbackQuery):
    """Callback orqali statistikani ko'rish."""
    telegram_id = callback.from_user.id
    async with AsyncSessionLocal() as session:
        u_stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(u_stmt)).scalar_one_or_none()
        if not user:
            await callback.answer("Foydalanuvchi topilmadi")
            return

        app_stmt = select(func.count()).select_from(Application).where(Application.user_id == user.id)
        total_applied = (await session.execute(app_stmt)).scalar() or 0

        vac_stmt = select(func.count()).select_from(Vacancy)
        total_vacancies = (await session.execute(vac_stmt)).scalar() or 0

        text = (
            "📊 <b>Sizning murojaatlar statistikangiz:</b>\n\n"
            f"🎯 Tanlangan lavozim: <b>{user.position or 'Belgilanmagan'}</b>\n"
            f"📍 Shahar: <b>{user.city or 'Belgilanmagan'}</b>\n"
            f"📨 Yuborilgan arizalar: <b>{total_applied} ta</b>\n"
            f"🗂 Bazadagi jami vakansiyalar: <b>{total_vacancies} ta</b>\n\n"
            "📥 Murojaatlar tarixini yuklab olish uchun: /export"
        )
        await callback.answer()
        await callback.message.answer(text)


@router.message(Command("export"))
async def cmd_export(message: Message):
    """Murojaatlar tarixini CSV fayl ko'rinishida yuborish."""
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

        # CSV fayl hosil qilish
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Manba", "Vakansiya", "Kompaniya", "Holati", "Sana", "Havola"])

        for app, vac in rows:
            writer.writerow([
                app.id,
                app.source,
                vac.title if vac else "Nomaʼlum",
                vac.company if vac else "",
                app.status.value if hasattr(app.status, "value") else str(app.status),
                app.applied_at.strftime("%Y-%m-%d %H:%M") if app.applied_at else "",
                vac.url if vac else "",
            ])

        csv_bytes = output.getvalue().encode("utf-8-sig")
        doc_file = BufferedInputFile(csv_bytes, filename="murojaatlar_tarixi.csv")

        await message.answer_document(
            document=doc_file,
            caption="📁 <b>Barcha murojaatlaringiz tarixi (CSV)</b>",
        )
