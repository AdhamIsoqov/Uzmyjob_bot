"""/ start handler — wizard boshlanishi."""
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "👋 <b>@Uzmyjob_bot</b>ga xush kelibsiz!\n\n"
        "Bu bot sizga O'zbekiston ish bozoridan "
        "vakansiyalarni topib, murojaat qilishga yordam beradi.\n\n"
        "Boshlash uchun /profil ni yuboring."
    )
