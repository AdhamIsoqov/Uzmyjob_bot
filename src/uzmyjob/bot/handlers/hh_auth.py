"""hh.uz OAuth2 buyruqlar handleri (/hh_login, /hh_code, /hh_status)."""
from datetime import UTC, datetime, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select

from uzmyjob.apply.hh_apply import HeadHunterApplyService
from uzmyjob.config import settings
from uzmyjob.models.base import AsyncSessionLocal
from uzmyjob.models.user import User
from uzmyjob.utils.crypto import encrypt_str

router = Router()


@router.message(Command("hh_login"))
async def cmd_hh_login(message: Message):
    """hh.uz bilan bog'lanish havolasini beradi."""
    hh_service = HeadHunterApplyService(
        client_id=settings.hh_client_id,
        client_secret=settings.hh_client_secret,
    )
    auth_url = hh_service.get_authorization_url(state=str(message.from_user.id))

    await message.answer(
        "🔗 <b>hh.uz hisobingizni ulash:</b>\n\n"
        f"1. <a href='{auth_url}'>Bu yerga bosing va hh.uz da ruxsat bering</a>.\n"
        "2. Ruxsat bergach, ochilgan sahifadagi <b>code</b> parametrini nusxalang.\n"
        "3. Botga quyidagicha yuboring:\n"
        "<code>/hh_code SIZNING_KODINGIZ</code>",
        disable_web_page_preview=True,
    )


@router.message(Command("hh_code"))
async def cmd_hh_code(message: Message):
    """Foydalanuvchi yuborgan avtorizatsiya kodini tokenlarga almashtiradi."""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("⚠️ Iltimos, kodni yozing: <code>/hh_code SIZNING_KODINGIZ</code>")
        return

    code = parts[1].strip()
    hh_service = HeadHunterApplyService(
        client_id=settings.hh_client_id,
        client_secret=settings.hh_client_secret,
    )

    await message.answer("⏳ Kod tekshirilmoqda va tokenlar olinmoqda...")
    token_data = await hh_service.exchange_code_for_token(code)

    if not token_data or "access_token" not in token_data:
        await message.answer(
            "❌ <b>Avtorizatsiya kodi yaroqsiz yoki muddati o'tgan.</b>\n"
            "Iltimos, /hh_login orqali yangi kod oling."
        )
        return

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 1209600)  # 14 kun default

    # Rezyumelarni tekshirib olamiz
    resumes = await hh_service.get_my_resumes(access_token)
    chosen_resume_id = None
    resume_title = "Standart rezyume"

    if resumes:
        chosen_resume_id = resumes[0].get("id")
        resume_title = resumes[0].get("title", resume_title)

    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()

        if not user:
            user = User(telegram_id=message.from_user.id)
            session.add(user)

        # Tokenlarni shifrlab saqlash
        user.hh_access_token_enc = encrypt_str(access_token)
        if refresh_token:
            user.hh_refresh_token_enc = encrypt_str(refresh_token)
        user.hh_token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        if chosen_resume_id:
            user.hh_resume_id = chosen_resume_id

        await session.commit()

    reply_text = (
        "✅ <b>hh.uz hisobingiz muvaffaqiyatli ulandi!</b>\n\n"
        f"📄 Faol rezyume: <b>{resume_title}</b>\n"
        f"🆔 Rezyume ID: <code>{chosen_resume_id or 'Topilmadi'}</code>\n\n"
        "Endi vakansiyalarga bir bosish bilan avtomatik murojaat qilishingiz mumkin!"
    )
    await message.answer(reply_text)


@router.message(Command("hh_status"))
async def cmd_hh_status(message: Message):
    """hh.uz ulanish holatini ko'rsatish."""
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()

        if not user or not user.hh_access_token_enc:
            await message.answer(
                "❌ <b>hh.uz hisobingiz ulanmagan.</b>\n"
                "Ulash uchun /hh_login buyrug'idan foydalaning."
            )
            return

        expires_str = (
            user.hh_token_expires_at.strftime("%Y-%m-%d %H:%M UTC")
            if user.hh_token_expires_at
            else "Nomaʼlum"
        )
        await message.answer(
            f"✅ <b>hh.uz hisobingiz faol!</b>\n"
            f"📄 Faol rezyume ID: <code>{user.hh_resume_id or 'Tanlanmagan'}</code>\n"
            f"⏳ Token amal qilish muddati: {expires_str}\n\n"
            "Qayta ulash uchun: /hh_login"
        )

