"""/start handler — botga kirish, til tanlash va FSM Wizard ga yo'naltirish."""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from sqlalchemy import select

from uzmyjob.bot.handlers.wizard import ProfileWizard
from uzmyjob.models.base import AsyncSessionLocal
from uzmyjob.models.user import Language, User
from uzmyjob.utils.logger import log

router = Router()


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Doimiy pastki navigatsiya menyusi."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="👤 Mening profilim"),
                KeyboardButton(text="💼 Vakansiyalar"),
            ],
            [
                KeyboardButton(text="📊 Statistika"),
                KeyboardButton(text="ℹ️ Yordam"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def get_language_keyboard() -> InlineKeyboardMarkup:
    """Til tanlash tugmalari."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="start_lang:uz"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="start_lang:ru"),
            ],
            [
                InlineKeyboardButton(text="🇬🇧 English", callback_data="start_lang:en"),
            ],
        ]
    )


def get_welcome_back_keyboard() -> InlineKeyboardMarkup:
    """Mavjud foydalanuvchilar uchun bosh menyu tugmalari."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚙️ Profilni ko'rish", callback_data="open_profile"),
                InlineKeyboardButton(text="📊 Statistika", callback_data="open_stats"),
            ],
            [
                InlineKeyboardButton(text="🔄 Profilni qayta sozlash", callback_data="start_wizard_flow"),
            ],
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Botga kirish komandasi."""
    if not message.from_user:
        return
    await state.clear()
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(stmt)).scalar_one_or_none()

        was_reactivated = False
        if user and not user.is_active:
            user.is_active = True
            await session.commit()
            was_reactivated = True
            log.info("user_reactivated", telegram_id=telegram_id)

        if user and user.position:
            user_name = escape(message.from_user.first_name or "Dasturchi")
            position_safe = escape(user.position)
            city_safe = escape(user.city or "Belgilanmagan")
            status_note = (
                "🔔 <b>Bildirishnomalar qayta faollashtirildi!</b>\n\n"
                if was_reactivated
                else ""
            )
            await message.answer(
                "📋 <b>Asosiy menyu faollashtirildi.</b> Quyidagi tugmalar orqali botni qulay boshqaring 👇",
                reply_markup=get_main_menu_keyboard(),
            )
            await message.answer(
                f"👋 <b>Qaytganingiz bilan, {user_name}!</b>\n\n"
                f"{status_note}"
                f"🎯 Hozirgi lavozim: <b>{position_safe}</b>\n"
                f"📍 Hudud: <b>{city_safe}</b>\n"
                f"🎯 Moslik chegarasi: <b>{int(user.match_threshold * 100)}%</b>\n\n"
                "Bot O'zbekiston ish platformalaridan (hh.uz, Telegram kanallari va RSS) "
                "sizga mos yangi vakansiyalarni qidirishda davom etmoqda.\n\n"
                "Quyidagi tugmalar orqali profilingizni boshqarishingiz mumkin:",
                reply_markup=get_welcome_back_keyboard(),
            )
            return

    # Yangi yoki to'liq profilga ega bo'lmagan foydalanuvchilar uchun til tanlash
    await message.answer(
        "👋 <b>@Uzmyjob_bot</b>ga xush kelibsiz!\n\n"
        "Bu bot sizga O'zbekiston ish bozoridan "
        "vakansiyalarni topib, qulay saralash va avtomatik murojaat qilishga yordam beradi.\n\n"
        "🌐 Iltimos, qulay muloqot tilini tanlang:\n"
        "Пожалуйста, выберите язык общения:\n"
        "Please select your preferred language:",
        reply_markup=get_language_keyboard(),
    )


@router.callback_query(F.data.startswith("start_lang:"))
async def process_start_lang(callback: CallbackQuery, state: FSMContext):
    """Til tanlangach, tilni saqlash va FSM Wizard'ni ishga tushirish."""
    await callback.answer()
    lang_code = callback.data.split(":")[1]
    telegram_id = callback.from_user.id

    lang_map = {
        "uz": Language.UZ,
        "ru": Language.RU,
        "en": Language.EN,
    }
    selected_lang = lang_map.get(lang_code, Language.UZ)

    try:
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.telegram_id == telegram_id)
            user = (await session.execute(stmt)).scalar_one_or_none()
            if not user:
                user = User(telegram_id=telegram_id, language=selected_lang)
                session.add(user)
            else:
                user.language = selected_lang
            await session.commit()
    except Exception as e:
        log.error("process_start_lang_db_error", error=str(e), telegram_id=telegram_id)

    try:
        if callback.message:
            await callback.message.delete()
    except Exception as e:
        log.warning("process_start_lang_delete_failed", error=str(e))

    await state.clear()
    await state.update_data(language=lang_code)

    await callback.bot.send_message(
        chat_id=telegram_id,
        text=(
            "🎯 <b>Profil sozlash (Wizard) boshlandi!</b>\n\n"
            "1-qadam: Qaysi <b>lavozim yoki mutaxassislik</b> bo'yicha ish qidiryapsiz?\n"
            "<i>(Masalan: Python Backend Developer, DevOps, Frontend React)</i>\n\n"
            "<i>Bekor qilish uchun istalgan vaqt /cancel deb yozishingiz mumkin.</i>"
        ),
        parse_mode="HTML",
    )
    await state.set_state(ProfileWizard.position)


@router.callback_query(F.data == "start_wizard_flow")
async def process_start_wizard_callback(callback: CallbackQuery, state: FSMContext):
    """Tugma orqali wizardni boshlash."""
    await callback.answer()
    telegram_id = callback.from_user.id
    try:
        if callback.message:
            await callback.message.delete()
    except Exception as e:
        log.warning("start_wizard_flow_delete_failed", error=str(e))

    await state.clear()
    await callback.bot.send_message(
        chat_id=telegram_id,
        text=(
            "🎯 <b>Profil sozlash (Wizard) boshlandi!</b>\n\n"
            "1-qadam: Qaysi <b>lavozim yoki mutaxassislik</b> bo'yicha ish qidiryapsiz?\n"
            "<i>(Masalan: Python Backend Developer, DevOps, Frontend React)</i>\n\n"
            "<i>Bekor qilish uchun istalgan vaqt /cancel deb yozishingiz mumkin.</i>"
        ),
        parse_mode="HTML",
    )
    await state.set_state(ProfileWizard.position)


@router.message(Command("help"))
@router.message(Command("yordam"))
@router.message(F.text == "ℹ️ Yordam")
async def cmd_help(message: Message):
    """Botdan foydalanish bo'yicha to'liq qo'llanma."""
    text = (
        "📖 <b>@Uzmyjob_bot Qo'llanma va Navigatsiya</b>\n\n"
        "Bot O'zbekiston ish bozoridan (hh.uz, Telegram kanallari va RSS manbalardan) "
        "vakansiyalarni to'plab, profilingizga moslarini aqlli saralab beradi.\n\n"
        "📌 <b>Asosiy bo'limlar:</b>\n"
        "• 👤 <b>Mening profilim (/profil)</b> — Qidiruv mezonlari, maosh, shahar va filtrlarni ko'rish hamda tahrirlash.\n"
        "• 💼 <b>Vakansiyalar (/vacancies)</b> — So'nggi mos vakansiyalarni darhol ko'rish.\n"
        "• 📊 <b>Statistika (/statistika)</b> — Yuborilgan arizalar va tizim tahlili.\n"
        "• 🔄 <b>Qayta sozlash (/wizard)</b> — Profilni boshidan to'ldirish.\n"
        "• 🔴 <b>hh.uz hisobi (/hh_login)</b> — Bir bosishda rezyume yuborish uchun OAuth2 ulash.\n\n"
        "Pastki menyudagi tugmalar orqali istalgan vaqtda kerakli bo'limga o'tishingiz mumkin! 👇"
    )
    await message.answer(text, reply_markup=get_main_menu_keyboard())


