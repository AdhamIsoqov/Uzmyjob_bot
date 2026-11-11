"""Foydalanuvchi profilini ko'rish va interaktiv tahrirlash handlerlari."""

import json
import re
from html import escape
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from uzmyjob.agents.cover_letter import validate_template
from uzmyjob.models.base import AsyncSessionLocal
from uzmyjob.models.user import User
from uzmyjob.utils.crypto import encrypt
from uzmyjob.utils.cv_parser import CVParser
from uzmyjob.utils.logger import log

router = Router()

MAX_CV_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


class EditFieldState(StatesGroup):
    waiting_for_position = State()
    waiting_for_city = State()
    waiting_for_experience = State()
    waiting_for_salary = State()
    waiting_for_employment = State()
    waiting_for_keywords = State()
    waiting_for_blacklist = State()
    waiting_for_cv = State()
    waiting_for_cover_letter = State()
    waiting_for_portfolio = State()


def get_profile_keyboard(auto_apply: bool) -> InlineKeyboardMarkup:
    """Profil boshqaruv tugmalari."""
    auto_apply_icon = "🟢 Yoqilgan" if auto_apply else "🔴 O'chirilgan"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Lavozim", callback_data="pedit:position"),
                InlineKeyboardButton(text="📍 Shahar", callback_data="pedit:city"),
            ],
            [
                InlineKeyboardButton(text="⏳ Tajriba", callback_data="pedit:experience"),
                InlineKeyboardButton(text="💰 Min maosh", callback_data="pedit:salary"),
            ],
            [
                InlineKeyboardButton(text="⏰ Bandlik turi", callback_data="pedit:employment"),
                InlineKeyboardButton(text="🔑 Kalit so'zlar", callback_data="pedit:keywords"),
            ],
            [
                InlineKeyboardButton(text="🚫 Qora ro'yxat", callback_data="pedit:blacklist"),
                InlineKeyboardButton(text="📄 Yangi CV yuklash", callback_data="pedit:cv"),
            ],
            [
                InlineKeyboardButton(text="✉️ Cover letter", callback_data="pedit:cover_letter"),
                InlineKeyboardButton(text="🌐 Portfolio", callback_data="pedit:portfolio"),
            ],
            [
                InlineKeyboardButton(text="🎯 Moslik chegarasi", callback_data="pedit:threshold"),
                InlineKeyboardButton(
                    text=f"⚡ Auto-apply: {auto_apply_icon}",
                    callback_data="ptoggle:auto_apply",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 To'liq qayta sozlash (/wizard)",
                    callback_data="start_wizard_flow",
                ),
            ],
        ]
    )


def get_threshold_keyboard() -> InlineKeyboardMarkup:
    """Moslik chegarasini tezkor tanlash."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="40%", callback_data="set_thresh:0.40"),
                InlineKeyboardButton(text="50%", callback_data="set_thresh:0.50"),
                InlineKeyboardButton(text="55% (Standart)", callback_data="set_thresh:0.55"),
            ],
            [
                InlineKeyboardButton(text="65%", callback_data="set_thresh:0.65"),
                InlineKeyboardButton(text="75%", callback_data="set_thresh:0.75"),
                InlineKeyboardButton(text="🔙 Orqaga", callback_data="open_profile"),
            ],
        ]
    )


def _format_profile_text(user: User) -> str:
    """Profil ma'lumotlarini XSS-xavfsiz HTML formatga keltirish."""
    keywords_list = json.loads(user.keywords) if user.keywords else []
    blacklist_list = json.loads(user.blacklist) if user.blacklist else []

    kw_str = escape(", ".join(str(k) for k in keywords_list)) if keywords_list else "Yo'q"
    bl_str = escape(", ".join(str(b) for b in blacklist_list)) if blacklist_list else "Yo'q"
    salary_str = (
        f"{user.min_salary:,}" if (user.min_salary and user.min_salary > 0) else "Belgilanmagan"
    )
    cv_status = "✅ Yuklangan (Fernet shifrlangan)" if user.cv_file_id else "❌ Yuklanmagan"
    cover_status = "Maxsus shablon" if user.cover_letter_template else "Standart rasmiy shablon"
    portfolio_str = escape(user.portfolio_links) if user.portfolio_links else "Kiritilmagan"
    auto_apply_str = "Yoqilgan" if user.auto_apply else "O'chirilgan"
    emp_safe = escape(user.employment_type or "To'liq bandlik")

    return (
        "⚙️ <b>Sizning profilingiz:</b>\n\n"
        f"🎯 <b>Lavozim:</b> {escape(user.position or 'Belgilanmagan')}\n"
        f"📍 <b>Shahar / Format:</b> {escape(user.city or 'Belgilanmagan')}\n"
        f"⏳ <b>Ish tajribasi:</b> {user.experience_years or 0} yil\n"
        f"💰 <b>Minimal maosh:</b> {salary_str}\n"
        f"⏰ <b>Bandlik turi:</b> {emp_safe}\n"
        f"🔑 <b>Kalit so'zlar:</b> {kw_str}\n"
        f"🚫 <b>Qora ro'yxat:</b> {bl_str}\n"
        f"📄 <b>Rezyume:</b> {cv_status}\n"
        f"✉️ <b>Cover Letter:</b> {cover_status}\n"
        f"🌐 <b>Portfolio:</b> {portfolio_str}\n"
        f"🎯 <b>Moslik chegarasi:</b> {int(user.match_threshold * 100)}%\n"
        f"⚡ <b>Auto-apply:</b> {auto_apply_str}\n\n"
        "O'zgartirish kiritish uchun quyidagi tugmalardan foydalaning:"
    )


async def _update_user_fields(telegram_id: int, **fields: Any) -> bool:
    """Foydalanuvchining ko'rsatilgan maydonlarini DB da yangilash."""
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if not user:
            return False
        for key, value in fields.items():
            setattr(user, key, value)
        await session.commit()
        return True


async def _require_text(message: Message) -> str | None:
    """Xabar matn ekanini tekshirish."""
    if not message.from_user:
        return None
    if not message.text or not message.text.strip():
        await message.answer("⚠️ Iltimos, matn ko'rinishida kiriting (bekor qilish: /cancel):")
        return None
    return message.text.strip()


def _parse_int_from_text(text: str, *, default: int = 0, maximum: int | None = None) -> int:
    """Matndan birinchi butun sonni xavfsiz ajratib olish."""
    nums = re.findall(r"\d+", text)
    if not nums:
        return default
    val = max(0, int(nums[0]))
    if maximum is not None:
        val = min(val, maximum)
    return val


@router.message(Command("profil"))
@router.message(Command("profile"))
@router.message(F.text == "👤 Mening profilim")
async def cmd_profil(message: Message, state: FSMContext):
    """/profil komandasi orqali profilni ko'rish."""
    if not message.from_user:
        return
    await state.clear()
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(stmt)).scalar_one_or_none()

        if not user or not user.position:
            await message.answer(
                "ℹ️ Siz hali profilingizni to'liq sozlamagansiz.\n"
                "Ish qidirishni boshlash uchun /wizard buyrug'ini yuboring."
            )
            return

        await message.answer(
            _format_profile_text(user),
            reply_markup=get_profile_keyboard(user.auto_apply),
        )


@router.callback_query(F.data == "open_profile")
async def process_open_profile_callback(callback: CallbackQuery, state: FSMContext):
    """Callback orqali profilni ochish."""
    await state.clear()
    telegram_id = callback.from_user.id

    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(stmt)).scalar_one_or_none()

        if not user or not user.position:
            await callback.answer("Profil mavjud emas")
            if callback.message:
                await callback.message.answer("Iltimos, avval /wizard orqali profilingizni sozlang.")
            return

        await callback.answer()
        if callback.message:
            await callback.message.edit_text(
                _format_profile_text(user),
                reply_markup=get_profile_keyboard(user.auto_apply),
            )


@router.callback_query(F.data == "ptoggle:auto_apply")
async def process_toggle_auto_apply(callback: CallbackQuery):
    """Auto-apply holatini yoqish/o'chirish."""
    telegram_id = callback.from_user.id
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if not user:
            await callback.answer("Profil topilmadi")
            return
        user.auto_apply = not user.auto_apply
        await session.commit()
        status_label = "Yoqildi" if user.auto_apply else "O'chirildi"
        await callback.answer(f"Auto-apply: {status_label}")
        if callback.message:
            await callback.message.edit_text(
                _format_profile_text(user),
                reply_markup=get_profile_keyboard(user.auto_apply),
            )


@router.callback_query(F.data == "pedit:threshold")
async def process_threshold_menu(callback: CallbackQuery):
    """Moslik chegarasini sozlash menyusi."""
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "🎯 <b>Vakansiyalarni moslik chegarasini (threshold) tanlang:</b>\n\n"
            "Masalan, 55% tanlasangiz, sizning profilingizga 55% va undan yuqori mos kelgan vakansiyalar yuboriladi.",
            reply_markup=get_threshold_keyboard(),
        )


@router.callback_query(F.data.startswith("set_thresh:"))
async def process_set_threshold(callback: CallbackQuery):
    """Yangi threshold qiymatini saqlash."""
    try:
        raw_val = float((callback.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Noto'g'ri qiymat.")
        return

    val = min(0.95, max(0.10, raw_val))
    telegram_id = callback.from_user.id
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user:
            user.match_threshold = val
            await session.commit()
            await callback.answer(f"Chegara {int(val * 100)}% ga o'zgartirildi")
            if callback.message:
                await callback.message.edit_text(
                    _format_profile_text(user),
                    reply_markup=get_profile_keyboard(user.auto_apply),
                )


_FIELD_PROMPTS: dict[str, tuple[str, State]] = {
    "position": (
        "✏️ Yangi <b>lavozim nomini</b> kiriting (bekor qilish: /cancel):",
        EditFieldState.waiting_for_position,
    ),
    "city": (
        "📍 Yangi <b>shahar yoki ish formatini</b> kiriting (bekor qilish: /cancel):",
        EditFieldState.waiting_for_city,
    ),
    "experience": (
        "⏳ <b>Ish tajribangizni</b> yillarda kiriting (masalan: 2, bekor qilish: /cancel):",
        EditFieldState.waiting_for_experience,
    ),
    "salary": (
        "💰 Kutilayotgan <b>minimal maoshni</b> kiriting (bekor qilish: /cancel):",
        EditFieldState.waiting_for_salary,
    ),
    "employment": (
        "⏰ Yangi <b>bandlik turini</b> kiriting (masalan: To'liq bandlik, Freelance):",
        EditFieldState.waiting_for_employment,
    ),
    "keywords": (
        "🔑 Yangi <b>kalit so'zlarni</b> vergul bilan ajratib yozing:",
        EditFieldState.waiting_for_keywords,
    ),
    "blacklist": (
        "🚫 Yangi <b>qora ro'yxat (blacklist)</b> so'zlarini vergul bilan ajratib yozing:",
        EditFieldState.waiting_for_blacklist,
    ),
    "cv": (
        "📄 Yangi <b>rezyumeni (PDF yoki DOCX, maks. 5 MB)</b> hujjat sifatida yuboring:",
        EditFieldState.waiting_for_cv,
    ),
    "cover_letter": (
        "✉️ Yangi <b>Cover letter (Jinja2)</b> shabloningizni yuboring\n"
        "(o'zgaruvchilar: <code>{{ vacancy_title }}</code>, <code>{{ company_name }}</code>):",
        EditFieldState.waiting_for_cover_letter,
    ),
    "portfolio": (
        "🌐 Yangi <b>portfolio yoki havolalarni</b> yuboring:",
        EditFieldState.waiting_for_portfolio,
    ),
}


@router.callback_query(F.data.startswith("pedit:"))
async def process_pedit_actions(callback: CallbackQuery, state: FSMContext):
    """Tahrirlash tugmasi bosilganda mos holatni yoqish."""
    field = (callback.data or "").split(":", 1)[1] if callback.data and ":" in callback.data else ""
    await callback.answer()
    entry = _FIELD_PROMPTS.get(field)
    if entry and callback.message:
        prompt_text, next_state = entry
        await callback.message.answer(prompt_text)
        await state.set_state(next_state)


@router.message(EditFieldState.waiting_for_position)
async def save_edited_position(message: Message, state: FSMContext):
    text = await _require_text(message)
    if text is None or not message.from_user:
        return
    if len(text) < 2:
        await message.answer("⚠️ Iltimos, lavozim nomini to'liqroq kiriting:")
        return
    await _update_user_fields(message.from_user.id, position=text[:200])
    await state.clear()
    await message.answer("✅ Lavozim yangilandi!")
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_city)
async def save_edited_city(message: Message, state: FSMContext):
    text = await _require_text(message)
    if text is None or not message.from_user:
        return
    await _update_user_fields(message.from_user.id, city=text[:100])
    await state.clear()
    await message.answer("✅ Shahar yangilandi!")
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_experience)
async def save_edited_experience(message: Message, state: FSMContext):
    text = await _require_text(message)
    if text is None or not message.from_user:
        return
    years = _parse_int_from_text(text, default=0, maximum=60)
    await _update_user_fields(message.from_user.id, experience_years=years)
    await state.clear()
    await message.answer(f"✅ Ish tajribasi {years} yil deb yangilandi!")
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_salary)
async def save_edited_salary(message: Message, state: FSMContext):
    text = await _require_text(message)
    if text is None or not message.from_user:
        return
    sal = _parse_int_from_text(text, default=0)
    await _update_user_fields(message.from_user.id, min_salary=sal)
    await state.clear()
    await message.answer(f"✅ Minimal maosh {sal:,} deb yangilandi!")
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_employment)
async def save_edited_employment(message: Message, state: FSMContext):
    text = await _require_text(message)
    if text is None or not message.from_user:
        return
    await _update_user_fields(message.from_user.id, employment_type=text[:100])
    await state.clear()
    await message.answer("✅ Bandlik turi yangilandi!")
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_keywords)
async def save_edited_keywords(message: Message, state: FSMContext):
    text = await _require_text(message)
    if text is None or not message.from_user:
        return
    kw_list = [k.strip() for k in text.split(",") if k.strip()][:50]
    await _update_user_fields(
        message.from_user.id,
        keywords=json.dumps(kw_list, ensure_ascii=False),
    )
    await state.clear()
    await message.answer("✅ Kalit so'zlar yangilandi!")
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_blacklist)
async def save_edited_blacklist(message: Message, state: FSMContext):
    text = await _require_text(message)
    if text is None or not message.from_user:
        return
    bl_list = [b.strip() for b in text.split(",") if b.strip()][:50]
    await _update_user_fields(
        message.from_user.id,
        blacklist=json.dumps(bl_list, ensure_ascii=False),
    )
    await state.clear()
    await message.answer("✅ Qora ro'yxat yangilandi!")
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_cv, F.document)
async def save_edited_cv(message: Message, state: FSMContext, bot: Bot):
    if not message.from_user or not message.document:
        return
    doc = message.document
    fname = doc.file_name or "resume.pdf"
    if not fname.lower().endswith((".pdf", ".docx")):
        await message.answer("⚠️ Iltimos, faqat <b>PDF</b> yoki <b>DOCX</b> formatidagi fayl yuboring:")
        return

    if doc.file_size and doc.file_size > MAX_CV_SIZE_BYTES:
        await message.answer("⚠️ Fayl hajmi juda katta (maksimum 5 MB ruxsat etilgan).")
        return

    await message.answer("⏳ Yangi rezyume tahlil qilinmoqda...")
    try:
        file_io = await bot.download(doc.file_id)
        if file_io is None:
            raise RuntimeError("Faylni Telegram serveridan yuklab bo'lmadi.")
        file_bytes = file_io.read()
        if len(file_bytes) > MAX_CV_SIZE_BYTES:
            await message.answer("⚠️ Fayl hajmi 5 MB dan oshmasligi kerak.")
            return

        parsed = CVParser.parse_cv(file_bytes, fname)
        encrypted_bytes = encrypt(file_bytes)

        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.telegram_id == message.from_user.id)
            user = (await session.execute(stmt)).scalar_one_or_none()
            if user:
                user.cv_file_id = doc.file_id[:200]
                user.cv_encrypted = encrypted_bytes

                current_kw = json.loads(user.keywords) if user.keywords else []
                for sk in parsed.get("detected_skills", []):
                    if sk.lower() not in [k.lower() for k in current_kw]:
                        current_kw.append(sk)
                user.keywords = json.dumps(current_kw[:50], ensure_ascii=False)
                await session.commit()

        skills_str = escape(", ".join(parsed.get("detected_skills", [])) or "topilmadi")
        await message.answer(
            f"✅ Yangi rezyume yuklandi va shifrlab saqlandi!\n💡 Aniqlangan ko'nikmalar: {skills_str}"
        )
    except Exception as e:
        log.error("edit_cv_failed", error=str(e))
        await message.answer(f"❌ Faylni tahlil qilishda xatolik: {escape(str(e))}")

    await state.clear()
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_cv)
async def save_edited_cv_non_document(message: Message):
    await message.answer(
        "⚠️ Iltimos, rezyumeni <b>PDF yoki DOCX hujjat (fayl)</b> sifatida yuboring (bekor qilish: /cancel)."
    )


@router.message(EditFieldState.waiting_for_cover_letter)
async def save_edited_cover_letter(message: Message, state: FSMContext):
    tpl = await _require_text(message)
    if tpl is None or not message.from_user:
        return
    is_valid, validation_msg = validate_template(tpl)
    if not is_valid:
        await message.answer(
            f"⚠️ Shablon xatosi:\n{escape(validation_msg)}\nIltimos, qayta yuboring:"
        )
        return

    await _update_user_fields(message.from_user.id, cover_letter_template=tpl[:4000])
    await state.clear()
    await message.answer("✅ Cover letter shabloni yangilandi!")
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_portfolio)
async def save_edited_portfolio(message: Message, state: FSMContext):
    portfolio = await _require_text(message)
    if portfolio is None or not message.from_user:
        return
    await _update_user_fields(message.from_user.id, portfolio_links=portfolio[:2000])
    await state.clear()
    await message.answer("✅ Portfolio havolalari yangilandi!")
    await cmd_profil(message, state)
