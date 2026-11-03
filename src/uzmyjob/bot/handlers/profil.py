"""/ profil handler."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("profil"))
async def cmd_profil(message: Message):
    await message.answer(
        "⚙️ <b>Profil sozlamalari</b>\n\n"
        "Bu bo'lim M3 da to'liq wizard bilan kengaytiriladi.\n"
        "Hozircha asosiy sozlamalar saqlanmoqda."
    )
