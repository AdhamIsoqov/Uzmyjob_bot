"""/stop va /delete_account handlerlari (GDPR-analog to'liq o'chirish)."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import delete, select

from uzmyjob.models.application import Application
from uzmyjob.models.base import AsyncSessionLocal
from uzmyjob.models.user import User
from uzmyjob.utils.logger import log

router = Router()


@router.message(Command("stop"))
async def cmd_stop(message: Message):
    """Bot faoliyatini vaqtinchalik to'xtatish (is_active = False)."""
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(stmt)).scalar_one_or_none()

        if user:
            user.is_active = False
            await session.commit()
            log.info("user_stopped_bot", telegram_id=telegram_id)

    await message.answer(
        "⏸ <b>Bot to'xtatildi.</b>\n"
        "Sizga yangi vakansiyalar yuborilmaydi.\n\n"
        "Qayta faollashtirish uchun: /start\n"
        "Barcha shaxsiy ma'lumotlarni o'chirish uchun: /delete_account"
    )


@router.message(Command("delete_account"))
async def cmd_delete_account(message: Message):
    """Foydalanuvchi va barcha unga tegishli arizalar, CV larni bazadan to'liq o'chirish."""
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(stmt)).scalar_one_or_none()

        if user:
            # 1. Userga tegishli barcha arizalarni o'chirish
            del_apps_stmt = delete(Application).where(Application.user_id == user.id)
            await session.execute(del_apps_stmt)

            # 2. Foydalanuvchi yozuvini o'chirish
            del_user_stmt = delete(User).where(User.id == user.id)
            await session.execute(del_user_stmt)

            await session.commit()
            log.info("user_account_deleted_completely", telegram_id=telegram_id)

    await message.answer(
        "🗑 <b>Hisobingiz va barcha ma'lumotlaringiz o'chirildi.</b>\n\n"
        "• Shaxsiy profil\n"
        "• Shifrlangan CV va rezyume matni\n"
        "• hh.uz OAuth tokenlari\n"
        "• Barcha yuborilgan arizalar tarixi\n\n"
        "Tizimdan to'liq tozalandi. Qayta foydalanish uchun /start bosing."
    )
