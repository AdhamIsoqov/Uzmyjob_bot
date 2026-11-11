"""/stop va /delete_account handlerlari (GDPR-analog to'liq o'chirish)."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import delete, select

from uzmyjob.models.application import Application
from uzmyjob.models.base import AsyncSessionLocal
from uzmyjob.models.user import User
from uzmyjob.utils.logger import log

router = Router()


def get_delete_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Hisobni o'chirishdan oldingi tasdiqlash tugmalari."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚠️ Ha, butunlay o'chirish",
                    callback_data="confirm_delete_account",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Bekor qilish",
                    callback_data="cancel_delete_account",
                )
            ],
        ]
    )


async def _perform_account_deletion(telegram_id: int) -> bool:
    """Foydalanuvchi va uning barcha yozuvlarini bazadan o'chirish."""
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if not user:
            return False

        await session.execute(delete(Application).where(Application.user_id == user.id))
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()
        log.info("user_account_deleted_completely", telegram_id=telegram_id)
        return True


@router.message(Command("stop"))
async def cmd_stop(message: Message):
    """Bot faoliyatini vaqtinchalik to'xtatish (is_active = False)."""
    if not message.from_user:
        return
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
    """Hisobni o'chirishdan oldin ikki bosqichli tasdiqlash so'rash."""
    if not message.from_user:
        return
    await message.answer(
        "⚠️ <b>Hisobni butunlay o'chirishni tasdiqlaysizmi?</b>\n\n"
        "Quyidagi barcha ma'lumotlar tiklanmas tarzda o'chiriladi:\n"
        "• Shaxsiy profil va sozlamalar\n"
        "• Shifrlangan CV va rezyume matni\n"
        "• hh.uz OAuth tokenlari\n"
        "• Barcha yuborilgan arizalar tarixi\n\n"
        "Davom etish uchun quyidagi tugmalardan birini tanlang:",
        reply_markup=get_delete_confirmation_keyboard(),
    )


@router.callback_query(F.data == "confirm_delete_account")
async def callback_confirm_delete_account(callback: CallbackQuery):
    """Hisob va barcha bog'liq ma'lumotlarni tasdiqlangandan keyin o'chirish."""
    telegram_id = callback.from_user.id
    await _perform_account_deletion(telegram_id)

    text = (
        "🗑 <b>Hisobingiz va barcha ma'lumotlaringiz o'chirildi.</b>\n\n"
        "• Shaxsiy profil\n"
        "• Shifrlangan CV va rezyume matni\n"
        "• hh.uz OAuth tokenlari\n"
        "• Barcha yuborilgan arizalar tarixi\n\n"
        "Tizimdan to'liq tozalandi. Qayta foydalanish uchun /start bosing."
    )
    if callback.message:
        await callback.message.edit_text(text)
    await callback.answer("Hisob o'chirildi.")


@router.callback_query(F.data == "cancel_delete_account")
async def callback_cancel_delete_account(callback: CallbackQuery):
    """Hisobni o'chirish amalini bekor qilish."""
    if callback.message:
        await callback.message.edit_text("✅ Hisobni o'chirish bekor qilindi. Ma'lumotlaringiz saqlab qolindi.")
    await callback.answer("Bekor qilindi.")
