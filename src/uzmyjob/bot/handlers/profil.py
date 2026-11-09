"""Foydalanuvchi profilini ko'rish va interaktiv tahrirlash handlerlari."""
import json
import re

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
                InlineKeyboardButton(text=f"⚡ Auto-apply: {auto_apply_icon}", callback_data="ptoggle:auto_apply"),
            ],
            [
                InlineKeyboardButton(text="🔄 To'liq qayta sozlash (/wizard)", callback_data="start_wizard_flow"),
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
    """Profil ma'lumotlarini chiroyli HTML formatga keltirish."""
    keywords_list = json.loads(user.keywords) if user.keywords else []
    blacklist_list = json.loads(user.blacklist) if user.blacklist else []

    kw_str = ", ".join(keywords_list) if keywords_list else "Yo'q"
    bl_str = ", ".join(blacklist_list) if blacklist_list else "Yo'q"
    salary_str = f"{user.min_salary:,}" if (user.min_salary and user.min_salary > 0) else "Belgilanmagan"
    cv_status = "✅ Yuklangan (AES-256 shifrlangan)" if user.cv_file_id else "❌ Yuklanmagan"
    cover_status = "Maxsus shablon" if user.cover_letter_template else "Standart rasmiy shablon"
    portfolio_str = user.portfolio_links or "Kiritilmagan"
    auto_apply_str = "Yoqilgan" if user.auto_apply else "O'chirilgan"

    return (
        "⚙️ <b>Sizning profilingiz:</b>\n\n"
        f"🎯 <b>Lavozim:</b> {user.position or 'Belgilanmagan'}\n"
        f"📍 <b>Shahar / Format:</b> {user.city or 'Belgilanmagan'}\n"
        f"⏳ <b>Ish tajribasi:</b> {user.experience_years or 0} yil\n"
        f"💰 <b>Minimal maosh:</b> {salary_str}\n"
        f"⏰ <b>Bandlik turi:</b> {user.employment_type or 'To\'liq bandlik'}\n"
        f"🔑 <b>Kalit so'zlar:</b> {kw_str}\n"
        f"🚫 <b>Qora ro'yxat:</b> {bl_str}\n"
        f"📄 <b>Rezyume:</b> {cv_status}\n"
        f"✉️ <b>Cover Letter:</b> {cover_status}\n"
        f"🌐 <b>Portfolio:</b> {portfolio_str}\n"
        f"🎯 <b>Moslik chegarasi:</b> {int(user.match_threshold * 100)}%\n"
        f"⚡ <b>Auto-apply:</b> {auto_apply_str}\n\n"
        "O'zgartirish kiritish uchun quyidagi tugmalardan foydalaning:"
    )


@router.message(Command("profil"))
@router.message(Command("profile"))
@router.message(F.text == "👤 Mening profilim")
async def cmd_profil(message: Message, state: FSMContext):
    """/profil komandasi orqali profilni ko'rish."""
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
            await callback.message.answer("Iltimos, avval /wizard orqali profilingizni sozlang.")
            return

        await callback.answer()
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
        if user:
            user.auto_apply = not user.auto_apply
            await session.commit()
            await callback.answer(f"Auto-apply: {'Yoqildi' if user.auto_apply else 'Ochirildi'}")
            await callback.message.edit_text(
                _format_profile_text(user),
                reply_markup=get_profile_keyboard(user.auto_apply),
            )


@router.callback_query(F.data == "pedit:threshold")
async def process_threshold_menu(callback: CallbackQuery):
    """Moslik chegarasini sozlash menyusi."""
    await callback.answer()
    await callback.message.edit_text(
        "🎯 <b>Vakansiyalarni moslik chegarasini (threshold) tanlang:</b>\n\n"
        "Masalan, 55% tanlasangiz, sizning profilingizga 55% va undan yuqori mos kelgan vakansiyalar yuboriladi.",
        reply_markup=get_threshold_keyboard(),
    )


@router.callback_query(F.data.startswith("set_thresh:"))
async def process_set_threshold(callback: CallbackQuery):
    """Yangi threshold qiymatini saqlash."""
    val = float(callback.data.split(":")[1])
    telegram_id = callback.from_user.id
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user:
            user.match_threshold = val
            await session.commit()
            await callback.answer(f"Chegara {int(val * 100)}% ga o'zgartirildi")
            await callback.message.edit_text(
                _format_profile_text(user),
                reply_markup=get_profile_keyboard(user.auto_apply),
            )


# Alohida maydonlarni tahrirlash bosqichlari
@router.callback_query(F.data.startswith("pedit:"))
async def process_pedit_actions(callback: CallbackQuery, state: FSMContext):
    """Tahrirlash tugmasi bosilganda mos holatni yoqish."""
    field = callback.data.split(":")[1]
    await callback.answer()

    if field == "position":
        await callback.message.answer("✏️ Yangi <b>lavozim nomini</b> kiriting (bekor qilish: /cancel):")
        await state.set_state(EditFieldState.waiting_for_position)
    elif field == "city":
        await callback.message.answer("📍 Yangi <b>shahar yoki ish formatini</b> kiriting (bekor qilish: /cancel):")
        await state.set_state(EditFieldState.waiting_for_city)
    elif field == "experience":
        await callback.message.answer("⏳ <b>Ish tajribangizni</b> yillarda kiriting (masalan: 2, bekor qilish: /cancel):")
        await state.set_state(EditFieldState.waiting_for_experience)
    elif field == "salary":
        await callback.message.answer("💰 Kutilayotgan <b>minimal maoshni</b> kiriting (bekor qilish: /cancel):")
        await state.set_state(EditFieldState.waiting_for_salary)
    elif field == "employment":
        await callback.message.answer("⏰ Yangi <b>bandlik turini</b> kiriting (masalan: To'liq bandlik, Freelance):")
        await state.set_state(EditFieldState.waiting_for_employment)
    elif field == "keywords":
        await callback.message.answer("🔑 Yangi <b>kalit so'zlarni</b> vergul bilan ajratib yozing:")
        await state.set_state(EditFieldState.waiting_for_keywords)
    elif field == "blacklist":
        await callback.message.answer("🚫 Yangi <b>qora ro'yxat (blacklist)</b> so'zlarini vergul bilan ajratib yozing:")
        await state.set_state(EditFieldState.waiting_for_blacklist)
    elif field == "cv":
        await callback.message.answer("📄 Yangi <b>rezyumeni (PDF yoki DOCX)</b> hujjat sifatida yuboring:")
        await state.set_state(EditFieldState.waiting_for_cv)
    elif field == "cover_letter":
        await callback.message.answer(
            "✉️ Yangi <b>Cover letter (Jinja2)</b> shabloningizni yuboring\n"
            "(o'zgaruvchilar: <code>{{ vacancy_title }}</code>, <code>{{ company_name }}</code>):"
        )
        await state.set_state(EditFieldState.waiting_for_cover_letter)
    elif field == "portfolio":
        await callback.message.answer("🌐 Yangi <b>portfolio yoki havolalarni</b> yuboring:")
        await state.set_state(EditFieldState.waiting_for_portfolio)


# Maydon javoblarini qabul qilish va yangilash
@router.message(EditFieldState.waiting_for_position)
async def save_edited_position(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user:
            user.position = message.text.strip()
            await session.commit()
    await state.clear()
    await message.answer("✅ Lavozim yangilandi!")
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_city)
async def save_edited_city(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user:
            user.city = message.text.strip()
            await session.commit()
    await state.clear()
    await message.answer("✅ Shahar yangilandi!")
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_experience)
async def save_edited_experience(message: Message, state: FSMContext):
    nums = re.findall(r"\d+", message.text)
    years = int(nums[0]) if nums else 0
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user:
            user.experience_years = years
            await session.commit()
    await state.clear()
    await message.answer(f"✅ Ish tajribasi {years} yil deb yangilandi!")
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_salary)
async def save_edited_salary(message: Message, state: FSMContext):
    nums = re.findall(r"\d+", message.text)
    sal = int(nums[0]) if nums else 0
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user:
            user.min_salary = sal
            await session.commit()
    await state.clear()
    await message.answer(f"✅ Minimal maosh {sal:,} deb yangilandi!")
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_employment)
async def save_edited_employment(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user:
            user.employment_type = message.text.strip()
            await session.commit()
    await state.clear()
    await message.answer("✅ Bandlik turi yangilandi!")
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_keywords)
async def save_edited_keywords(message: Message, state: FSMContext):
    kw_list = [k.strip() for k in message.text.split(",") if k.strip()]
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user:
            user.keywords = json.dumps(kw_list, ensure_ascii=False)
            await session.commit()
    await state.clear()
    await message.answer("✅ Kalit so'zlar yangilandi!")
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_blacklist)
async def save_edited_blacklist(message: Message, state: FSMContext):
    bl_list = [b.strip() for b in message.text.split(",") if b.strip()]
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user:
            user.blacklist = json.dumps(bl_list, ensure_ascii=False)
            await session.commit()
    await state.clear()
    await message.answer("✅ Qora ro'yxat yangilandi!")
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_cv, F.document)
async def save_edited_cv(message: Message, state: FSMContext, bot: Bot):
    doc = message.document
    fname = doc.file_name or "resume.pdf"
    if not fname.lower().endswith((".pdf", ".docx", ".doc")):
        await message.answer("⚠️ Iltimos, faqat PDF yoki DOCX formatidagi fayl yuboring:")
        return

    await message.answer("⏳ Yangi rezyume tahlil qilinmoqda...")
    try:
        file_io = await bot.download(doc.file_id)
        file_bytes = file_io.read()
        parsed = CVParser.parse_cv(file_bytes, fname)
        encrypted_bytes = encrypt(file_bytes)

        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.telegram_id == message.from_user.id)
            user = (await session.execute(stmt)).scalar_one_or_none()
            if user:
                user.cv_file_id = doc.file_id
                user.cv_encrypted = encrypted_bytes

                # Agar yangi ko'nikmalar topilgan bo'lsa, kalit so'zlarga qo'shish
                current_kw = json.loads(user.keywords) if user.keywords else []
                for sk in parsed.get("detected_skills", []):
                    if sk.lower() not in [k.lower() for k in current_kw]:
                        current_kw.append(sk)
                user.keywords = json.dumps(current_kw, ensure_ascii=False)
                await session.commit()

        skills_str = ", ".join(parsed.get("detected_skills", [])) or "topilmadi"
        await message.answer(f"✅ Yangi rezyume yuklandi va shifrlab saqlandi!\n💡 Aniqlangan ko'nikmalar: {skills_str}")
    except Exception as e:
        log.error("edit_cv_failed", error=str(e))
        await message.answer(f"❌ Faylni yuklashda xatolik: {e!s}")

    await state.clear()
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_cover_letter)
async def save_edited_cover_letter(message: Message, state: FSMContext):
    tpl = message.text.strip()
    is_valid, validation_msg = validate_template(tpl)
    if not is_valid:
        await message.answer(f"⚠️ Shablon xatosi:\n{validation_msg}\nIltimos, qayta yuboring:")
        return

    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user:
            user.cover_letter_template = tpl
            await session.commit()

    await state.clear()
    await message.answer("✅ Cover letter shabloni yangilandi!")
    await cmd_profil(message, state)


@router.message(EditFieldState.waiting_for_portfolio)
async def save_edited_portfolio(message: Message, state: FSMContext):
    portfolio = message.text.strip()
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user:
            user.portfolio_links = portfolio
            await session.commit()

    await state.clear()
    await message.answer("✅ Portfolio havolalari yangilandi!")
    await cmd_profil(message, state)
