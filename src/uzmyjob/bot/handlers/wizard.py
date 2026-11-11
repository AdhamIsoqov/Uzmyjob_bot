"""Foydalanuvchi profilini sozlash va rezyume yuklash uchun to'liq Telegram FSM Wizard."""

import json
import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)
from sqlalchemy import select

from uzmyjob.agents.cover_letter import get_default_template, validate_template
from uzmyjob.models.base import AsyncSessionLocal
from uzmyjob.models.user import User
from uzmyjob.pipeline.pipeline import JobPipeline
from uzmyjob.utils.crypto import encrypt
from uzmyjob.utils.cv_parser import CVParser
from uzmyjob.utils.logger import log

router = Router()

MAX_CV_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


class ProfileWizard(StatesGroup):
    """FSM Wizard bosqichlari."""

    position = State()
    city = State()
    experience = State()
    min_salary = State()
    employment_type = State()
    keywords = State()
    blacklist = State()
    cv_upload = State()
    cover_letter = State()
    portfolio = State()
    confirm = State()


def get_city_shortcuts_keyboard() -> InlineKeyboardMarkup:
    """Shahar tezkor tanlov tugmalari."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📍 Toshkent", callback_data="wiz_city:Toshkent"),
                InlineKeyboardButton(text="📍 Samarqand", callback_data="wiz_city:Samarqand"),
            ],
            [
                InlineKeyboardButton(text="🌐 Masofaviy (Remote)", callback_data="wiz_city:Remote"),
            ],
        ]
    )


def get_employment_keyboard() -> InlineKeyboardMarkup:
    """Bandlik turi tugmalari."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏢 To'liq bandlik (Full-time)",
                    callback_data="wiz_emp:To'liq bandlik",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⏳ Yarim bandlik (Part-time)",
                    callback_data="wiz_emp:Yarim bandlik",
                ),
                InlineKeyboardButton(
                    text="💼 Loyiha (Project)",
                    callback_data="wiz_emp:Loyiha asosida",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🌐 Freelance / Masofaviy",
                    callback_data="wiz_emp:Freelance",
                ),
                InlineKeyboardButton(
                    text="🔄 Hammasi ma'qul",
                    callback_data="wiz_emp:Istalgan",
                ),
            ],
        ]
    )


def get_confirm_keyboard() -> InlineKeyboardMarkup:
    """Wizard yakuniy tasdiqlash tugmalari."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Tasdiqlash va saqlash",
                    callback_data="wiz_confirm:save",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Qayta boshlash",
                    callback_data="wiz_confirm:restart",
                ),
                InlineKeyboardButton(
                    text="❌ Bekor qilish",
                    callback_data="wiz_confirm:cancel",
                ),
            ],
        ]
    )


def _extract_digits(text: str, default: int = 0) -> int:
    """Matndan sonlarni ajratib olish."""
    matches = re.findall(r"\d+", text)
    if matches:
        try:
            return max(0, int(matches[0]))
        except ValueError:
            return default
    return default


async def _require_text(message: Message) -> str | None:
    """Foydalanuvchi xabarida bo'sh bo'lmagan matn borligini tekshirish."""
    if not message.text or not message.text.strip():
        await message.answer("⚠️ Iltimos, javobni matn ko'rinishida yuboring (bekor qilish: /cancel):")
        return None
    return message.text.strip()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Wizard jarayonini istalgan qadamda to'xtatish."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("ℹ️ Hech qanday faol jarayon mavjud emas.")
        return
    await state.clear()
    await message.answer(
        "🚫 <b>Jarayon bekor qilindi.</b>\n"
        "Profilingizni qayta sozlash uchun /wizard yoki /profil buyrug'ini yuborishingiz mumkin.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(Command("wizard"))
async def start_wizard_command(message: Message, state: FSMContext):
    """Wizard'ni noldan boshlash."""
    await state.clear()
    await message.answer(
        "🎯 <b>Profil sozlash (Wizard) boshlandi!</b>\n\n"
        "1-qadam: Qaysi <b>lavozim yoki mutaxassislik</b> bo'yicha ish qidiryapsiz?\n"
        "<i>(Masalan: Python Backend Developer, DevOps, Frontend React)</i>\n\n"
        "<i>Istalgan vaqt jarayonni to'xtatish uchun /cancel deb yozing.</i>",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(ProfileWizard.position)


# 1. Lavozim
@router.message(ProfileWizard.position)
async def process_position(message: Message, state: FSMContext):
    pos = await _require_text(message)
    if pos is None:
        return
    pos = pos[:200]
    if len(pos) < 2:
        await message.answer("⚠️ Iltimos, lavozim nomini to'liqroq yozing:")
        return

    await state.update_data(position=pos)
    await message.answer(
        "📍 2-qadam: Qaysi <b>shahar yoki formatda</b> ishlamoqchisiz?\n"
        "Quyidagi tugmalardan birini tanlang yoki o'zingiz yozing:",
        reply_markup=get_city_shortcuts_keyboard(),
    )
    await state.set_state(ProfileWizard.city)


# 2. Shahar
@router.callback_query(ProfileWizard.city, F.data.startswith("wiz_city:"))
async def process_city_callback(callback: CallbackQuery, state: FSMContext):
    city = (callback.data or "").split(":", 1)[1][:100]
    await callback.answer()
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await callback.message.answer(
            f"✅ Shahar: <b>{escape(city)}</b>\n\n"
            "⏳ 3-qadam: Necha yillik <b>ish tajribasiga</b> egasiz?\n"
            "<i>(Faqat son yozing, masalan: 0, 2, 4)</i>"
        )
    await state.update_data(city=city)
    await state.set_state(ProfileWizard.experience)


@router.message(ProfileWizard.city)
async def process_city_text(message: Message, state: FSMContext):
    city = await _require_text(message)
    if city is None:
        return
    city = city[:100]
    await state.update_data(city=city)
    await message.answer(
        f"✅ Shahar: <b>{escape(city)}</b>\n\n"
        "⏳ 3-qadam: Necha yillik <b>ish tajribasiga</b> egasiz?\n"
        "<i>(Faqat son yozing, masalan: 0, 2, 4)</i>"
    )
    await state.set_state(ProfileWizard.experience)


# 3. Tajriba
@router.message(ProfileWizard.experience)
async def process_experience(message: Message, state: FSMContext):
    text = await _require_text(message)
    if text is None:
        return
    years = min(60, _extract_digits(text, default=1))
    await state.update_data(experience=years)
    await message.answer(
        f"✅ Tajriba: <b>{years} yil</b>\n\n"
        "💰 4-qadam: Kutilayotgan <b>minimal maosh</b> miqdori qancha?\n"
        "<i>(Masalan: 800 yoki 10000000. Agar muhim bo'lmasa, 0 yoki /skip deb yozing)</i>"
    )
    await state.set_state(ProfileWizard.min_salary)


# 4. Minimal maosh
@router.message(ProfileWizard.min_salary, Command("skip"))
async def process_salary_skip(message: Message, state: FSMContext):
    await state.update_data(min_salary=0)
    await message.answer(
        "✅ Maosh chegarasi belgilanmadi.\n\n"
        "⏰ 5-qadam: Qaysi <b>bandlik turi</b> ma'qul?",
        reply_markup=get_employment_keyboard(),
    )
    await state.set_state(ProfileWizard.employment_type)


@router.message(ProfileWizard.min_salary)
async def process_salary(message: Message, state: FSMContext):
    text = await _require_text(message)
    if text is None:
        return
    salary = _extract_digits(text, default=0)
    await state.update_data(min_salary=salary)
    sal_text = f"{salary:,}" if salary > 0 else "Belgilanmadi"
    await message.answer(
        f"✅ Minimal maosh: <b>{sal_text}</b>\n\n"
        "⏰ 5-qadam: Qaysi <b>bandlik turi</b> ma'qul?",
        reply_markup=get_employment_keyboard(),
    )
    await state.set_state(ProfileWizard.employment_type)


# 5. Bandlik turi
@router.callback_query(ProfileWizard.employment_type, F.data.startswith("wiz_emp:"))
async def process_employment_callback(callback: CallbackQuery, state: FSMContext):
    emp_type = (callback.data or "").split(":", 1)[1][:100]
    await callback.answer()
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await callback.message.answer(
            f"✅ Bandlik turi: <b>{escape(emp_type)}</b>\n\n"
            "🔑 6-qadam: Vakansiyalarda qidiriladigan <b>kalit so'zlar / texnologiyalarni</b> yozing:\n"
            "<i>(Vergul bilan ajrating, masalan: Python, FastAPI, PostgreSQL, Docker)</i>"
        )
    await state.update_data(employment_type=emp_type)
    await state.set_state(ProfileWizard.keywords)


@router.message(ProfileWizard.employment_type)
async def process_employment_text(message: Message, state: FSMContext):
    emp_type = await _require_text(message)
    if emp_type is None:
        return
    emp_type = emp_type[:100]
    await state.update_data(employment_type=emp_type)
    await message.answer(
        f"✅ Bandlik turi: <b>{escape(emp_type)}</b>\n\n"
        "🔑 6-qadam: Vakansiyalarda qidiriladigan <b>kalit so'zlar / texnologiyalarni</b> yozing:\n"
        "<i>(Vergul bilan ajrating, masalan: Python, FastAPI, PostgreSQL, Docker)</i>"
    )
    await state.set_state(ProfileWizard.keywords)


# 6. Kalit so'zlar
@router.message(ProfileWizard.keywords)
async def process_keywords(message: Message, state: FSMContext):
    text = await _require_text(message)
    if text is None:
        return
    raw_kw = [k.strip() for k in text.split(",") if k.strip()][:50]
    if not raw_kw:
        await message.answer("⚠️ Iltimos, kamida bitta kalit so'z yozing:")
        return

    await state.update_data(keywords=raw_kw)
    await message.answer(
        f"✅ Kalit so'zlar: <b>{escape(', '.join(raw_kw))}</b>\n\n"
        "🚫 7-qadam: <b>Qora ro'yxat (Blacklist)</b> — qaysi so'zlar qatnashgan vakansiyalarni ko'rsatmaylik?\n"
        "<i>(Vergul bilan ajrating, masalan: стажировка, amaliyot, piramida, 1xbet)\n"
        "Agar qora ro'yxat kerak bo'lmasa, /skip deb yozing.</i>"
    )
    await state.set_state(ProfileWizard.blacklist)


# 7. Qora ro'yxat (Blacklist)
@router.message(ProfileWizard.blacklist, Command("skip"))
async def process_blacklist_skip(message: Message, state: FSMContext):
    await state.update_data(blacklist=[])
    await message.answer(
        "✅ Qora ro'yxat bo'sh qoldirildi.\n\n"
        "📄 8-qadam: <b>Rezyumeingizni (CV) hujjat (document) ko'rinishida yuboring</b> "
        "(PDF yoki DOCX, maks. 5 MB).\n\n"
        "💡 <i>Bot rezyumedagi ko'nikmalarni avtomatik o'qiydi va faylni Fernet bilan shifrlab saqlaydi.\n"
        "Hozir yuklamoqchi bo'lmasangiz, /skip deb yozing.</i>"
    )
    await state.set_state(ProfileWizard.cv_upload)


@router.message(ProfileWizard.blacklist)
async def process_blacklist(message: Message, state: FSMContext):
    text = await _require_text(message)
    if text is None:
        return
    raw_bl = [b.strip() for b in text.split(",") if b.strip()][:50]
    await state.update_data(blacklist=raw_bl)
    await message.answer(
        f"✅ Qora ro'yxat: <b>{escape(', '.join(raw_bl))}</b>\n\n"
        "📄 8-qadam: <b>Rezyumeingizni (CV) hujjat (document) ko'rinishida yuboring</b> "
        "(PDF yoki DOCX, maks. 5 MB).\n\n"
        "💡 <i>Bot rezyumedagi ko'nikmalarni avtomatik o'qiydi va faylni Fernet bilan shifrlab saqlaydi.\n"
        "Hozir yuklamoqchi bo'lmasangiz, /skip deb yozing.</i>"
    )
    await state.set_state(ProfileWizard.cv_upload)


# 8. CV Yuklash va tahlil qilish
@router.message(ProfileWizard.cv_upload, F.document)
async def process_cv_document(message: Message, state: FSMContext, bot: Bot):
    doc = message.document
    if not doc:
        return
    fname = doc.file_name or "resume.pdf"
    if not fname.lower().endswith((".pdf", ".docx")):
        await message.answer(
            "⚠️ Iltimos, faqat <b>PDF</b> yoki <b>DOCX</b> formatidagi hujjat yuboring (yoki /skip bosing):"
        )
        return

    if doc.file_size and doc.file_size > MAX_CV_SIZE_BYTES:
        await message.answer(
            "⚠️ Fayl hajmi 5 MB dan katta. Kichikroq fayl yuboring yoki /skip bosing:"
        )
        return

    await message.answer("⏳ Rezyume yuklanmoqda va tahlil qilinmoqda...")

    try:
        file_io = await bot.download(doc.file_id)
        if file_io is None:
            raise RuntimeError("Faylni yuklab bo'lmadi.")
        file_bytes = file_io.read()
        if len(file_bytes) > MAX_CV_SIZE_BYTES:
            await message.answer("⚠️ Fayl hajmi 5 MB dan oshmasligi kerak.")
            return

        parsed = CVParser.parse_cv(file_bytes, fname)
        encrypted_bytes = encrypt(file_bytes)

        await state.update_data(
            cv_file_id=doc.file_id[:200],
            cv_file_name=fname[:200],
            cv_encrypted=encrypted_bytes.decode("latin1"),
            cv_detected_skills=parsed.get("detected_skills", []),
            cv_phone=parsed.get("phone", ""),
            cv_email=parsed.get("email", ""),
            cv_github=parsed.get("github", ""),
            cv_linkedin=parsed.get("linkedin", ""),
        )

        data = await state.get_data()
        existing_keywords = data.get("keywords", [])
        new_skills = [
            s
            for s in parsed.get("detected_skills", [])
            if s.lower() not in [k.lower() for k in existing_keywords]
        ]
        if new_skills:
            existing_keywords.extend(new_skills[:10])
            await state.update_data(keywords=existing_keywords[:50])

        skills_str = escape(", ".join(parsed.get("detected_skills", [])) or "aniqlanmadi")
        contacts_info = []
        if parsed.get("email"):
            contacts_info.append(f"📧 {escape(parsed['email'])}")
        if parsed.get("phone"):
            contacts_info.append(f"📞 {escape(parsed['phone'])}")
        if parsed.get("github"):
            contacts_info.append(f"🐙 {escape(parsed['github'])}")

        contacts_str = "\n".join(contacts_info) if contacts_info else "Kontaktlar topilmadi"

        await message.answer(
            f"✅ <b>Rezyume qabul qilindi va tahlil qilindi!</b>\n\n"
            f"📄 Fayl: <b>{escape(fname)}</b>\n"
            f"🛠 CV dan topilgan ko'nikmalar: <i>{skills_str}</i>\n"
            f"{contacts_str}\n\n"
            "✉️ 9-qadam: <b>Cover Letter (Murojaat xabari) shabloni</b>.\n"
            "O'zingizning maxsus Jinja2 shabloningizni yuborishingiz mumkin "
            "(o'zgaruvchilar: <code>{{ vacancy_title }}</code>, <code>{{ company_name }}</code>, "
            "<code>{{ position }}</code>).\n\n"
            "Standart rasmiy shablondan foydalanish uchun /skip deb yozing."
        )
    except Exception as e:
        log.error("cv_parsing_failed", error=str(e))
        await message.answer(
            f"⚠️ Faylni tahlil qilishda xatolik: {escape(str(e))}\n"
            "Qaytadan PDF/DOCX yuborishingiz yoki /skip bosib davom etishingiz mumkin.\n\n"
            "✉️ 9-qadam: Cover letter shablonini kiriting yoki /skip deb yozing:"
        )

    await state.set_state(ProfileWizard.cover_letter)


@router.message(ProfileWizard.cv_upload, Command("skip"))
async def process_cv_skip(message: Message, state: FSMContext):
    await state.update_data(cv_file_id=None, cv_file_name=None, cv_encrypted=None)
    await message.answer(
        "✅ Rezyume yuklash o'tkazib yuborildi.\n\n"
        "✉️ 9-qadam: <b>Cover Letter (Murojaat xabari) shabloni</b>.\n"
        "O'zingizning maxsus Jinja2 shabloningizni yuborishingiz mumkin "
        "(o'zgaruvchilar: <code>{{ vacancy_title }}</code>, <code>{{ company_name }}</code>, "
        "<code>{{ position }}</code>).\n\n"
        "Standart rasmiy shablondan foydalanish uchun /skip deb yozing."
    )
    await state.set_state(ProfileWizard.cover_letter)


@router.message(ProfileWizard.cv_upload)
async def process_cv_non_document(message: Message):
    await message.answer(
        "⚠️ Iltimos, rezyumeni <b>PDF yoki DOCX hujjat (fayl)</b> sifatida yuboring yoki /skip deb yozing."
    )


# 9. Cover Letter Shabloni
@router.message(ProfileWizard.cover_letter, Command("skip"))
async def process_cover_letter_skip(message: Message, state: FSMContext):
    data = await state.get_data()
    default_tpl = get_default_template(data.get("language", "uz"))
    await state.update_data(cover_letter_template=default_tpl)
    await message.answer(
        "✅ Standart Cover letter shabloni tanlandi.\n\n"
        "🌐 10-qadam: <b>Portfolio / Havolalar</b>.\n"
        "GitHub, LinkedIn, Behance yoki shaxsiy portfolio havolalarini yuboring.\n"
        "<i>(Agar hozircha yo'q bo'lsa, /skip deb yozing)</i>"
    )
    await state.set_state(ProfileWizard.portfolio)


@router.message(ProfileWizard.cover_letter)
async def process_cover_letter_custom(message: Message, state: FSMContext):
    tpl_text = await _require_text(message)
    if tpl_text is None:
        return
    is_valid, validation_msg = validate_template(tpl_text)
    if not is_valid:
        await message.answer(
            f"⚠️ <b>Shablonda xatolik topildi:</b>\n<i>{escape(validation_msg)}</i>\n\n"
            "Iltimos, shablonni to'g'rilab qayta yuboring yoki standart shablon uchun /skip deb yozing."
        )
        return

    await state.update_data(cover_letter_template=tpl_text[:4000])
    await message.answer(
        "✅ Cover letter shabloni qabul qilindi.\n\n"
        "🌐 10-qadam: <b>Portfolio / Havolalar</b>.\n"
        "GitHub, LinkedIn, Behance yoki shaxsiy portfolio havolalarini yuboring.\n"
        "<i>(Agar hozircha yo'q bo'lsa, /skip deb yozing)</i>"
    )
    await state.set_state(ProfileWizard.portfolio)


# 10. Portfolio havolalari
@router.message(ProfileWizard.portfolio, Command("skip"))
async def process_portfolio_skip(message: Message, state: FSMContext):
    data = await state.get_data()
    cv_links = []
    if data.get("cv_github"):
        cv_links.append(data["cv_github"])
    if data.get("cv_linkedin"):
        cv_links.append(data["cv_linkedin"])
    portfolio_val = "\n".join(cv_links)[:2000] if cv_links else None
    await state.update_data(portfolio_links=portfolio_val)

    await _show_profile_confirmation(message, state)


@router.message(ProfileWizard.portfolio)
async def process_portfolio(message: Message, state: FSMContext):
    portfolio_text = await _require_text(message)
    if portfolio_text is None:
        return
    await state.update_data(portfolio_links=portfolio_text[:2000])
    await _show_profile_confirmation(message, state)


# 11. Xulosa va tasdiqlash
async def _show_profile_confirmation(message: Message, state: FSMContext):
    """Barcha to'plangan ma'lumotlarni foydalanuvchiga XSS-xavfsiz taqdim etish."""
    data = await state.get_data()

    pos = escape(str(data.get("position", "Belgilanmagan")))
    city = escape(str(data.get("city", "Belgilanmagan")))
    exp = data.get("experience", 0)
    salary = data.get("min_salary", 0)
    salary_str = f"{salary:,}" if salary > 0 else "Belgilanmagan"
    emp_type = escape(str(data.get("employment_type", "Istalgan")))
    keywords = escape(", ".join(data.get("keywords", [])) or "Yo'q")
    blacklist = escape(", ".join(data.get("blacklist", [])) or "Yo'q")
    cv_raw = data.get("cv_file_name") or ("Yuklangan" if data.get("cv_file_id") else "Yuklanmagan")
    cv_file = escape(str(cv_raw))
    portfolio = escape(str(data.get("portfolio_links") or "Kiritilmagan"))

    summary_text = (
        "📋 <b>Profilingiz xulosasi:</b>\n\n"
        f"🎯 <b>Lavozim:</b> {pos}\n"
        f"📍 <b>Shahar / Format:</b> {city}\n"
        f"⏳ <b>Ish tajribasi:</b> {exp} yil\n"
        f"💰 <b>Minimal maosh:</b> {salary_str}\n"
        f"⏰ <b>Bandlik turi:</b> {emp_type}\n"
        f"🔑 <b>Kalit so'zlar:</b> {keywords}\n"
        f"🚫 <b>Qora ro'yxat:</b> {blacklist}\n"
        f"📄 <b>Rezyume (CV):</b> {cv_file}\n"
        f"🌐 <b>Portfolio:</b> {portfolio}\n\n"
        "Ma'lumotlar to'g'riligini tasdiqlaysizmi?"
    )

    await message.answer(summary_text, reply_markup=get_confirm_keyboard())
    await state.set_state(ProfileWizard.confirm)


@router.callback_query(ProfileWizard.confirm, F.data == "wiz_confirm:save")
async def process_confirm_save(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Profilni bazada saqlash va backfill yuborish."""
    await callback.answer("Profil saqlanmoqda...")
    data = await state.get_data()
    telegram_id = callback.from_user.id

    cv_enc_bytes = None
    if data.get("cv_encrypted"):
        cv_enc_bytes = data["cv_encrypted"].encode("latin1")

    await _save_user_profile(
        telegram_id=telegram_id,
        data=data,
        cv_file_id=data.get("cv_file_id"),
        cv_encrypted=cv_enc_bytes,
    )

    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        from uzmyjob.bot.handlers.start import get_main_menu_keyboard

        await callback.message.answer(
            "🎉 <b>Tabriklaymiz! Profilingiz muvaffaqiyatli saqlandi!</b>\n\n"
            "🔍 Bot endi so'nggi kunlardagi sizga mos vakansiyalarni tekshirmoqda...",
            reply_markup=get_main_menu_keyboard(),
        )
    await state.clear()

    try:
        pipeline = JobPipeline(bot=bot)
        notified = await pipeline.backfill_for_user(telegram_id, limit=3)
        if notified > 0:
            await bot.send_message(
                chat_id=telegram_id,
                text=(
                    f"✨ So'nggi vakansiyalar bazasidan profilingizga mos <b>{notified} ta</b> "
                    "taklif topildi (yuqorida ko'rishingiz mumkin)."
                ),
            )
        else:
            await bot.send_message(
                chat_id=telegram_id,
                text=(
                    "ℹ️ Hozircha bazada to'liq mos keluvchi yangi vakansiya topilmadi. "
                    "Yangi e'lonlar paydo bo'lishi bilan bot sizga darhol xabar beradi!"
                ),
            )
    except Exception as e:
        log.error("wizard_backfill_failed", error=str(e))


@router.callback_query(ProfileWizard.confirm, F.data == "wiz_confirm:restart")
async def process_confirm_restart(callback: CallbackQuery, state: FSMContext):
    """Qayta boshlash."""
    await callback.answer()
    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            "🔄 <b>Profilni sozlash qaytadan boshlandi.</b>\n\n"
            "1-qadam: Qaysi <b>lavozim yoki mutaxassislik</b> bo'yicha ish qidiryapsiz?\n"
            "<i>(Masalan: Python Backend Developer, DevOps, Frontend React)</i>"
        )
    await state.clear()
    await state.set_state(ProfileWizard.position)


@router.callback_query(ProfileWizard.confirm, F.data == "wiz_confirm:cancel")
async def process_confirm_cancel(callback: CallbackQuery, state: FSMContext):
    """Bekor qilish."""
    await callback.answer()
    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            "🚫 Profil sozlash bekor qilindi. Istalgan vaqt /wizard orqali qayta sozlashingiz mumkin."
        )
    await state.clear()


async def _save_user_profile(
    telegram_id: int,
    data: dict,
    cv_file_id: str | None,
    cv_encrypted: bytes | None,
):
    """Foydalanuvchi ma'lumotlarini bazada saqlash."""
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(stmt)).scalar_one_or_none()

        if not user:
            user = User(telegram_id=telegram_id)
            session.add(user)

        pos = data.get("position")
        city = data.get("city")
        emp_type = data.get("employment_type", "To'liq bandlik")

        user.position = pos[:200] if pos else None
        user.city = city[:100] if city else None
        user.experience_years = data.get("experience", 0)
        user.min_salary = data.get("min_salary", 0)
        user.employment_type = emp_type[:100] if emp_type else None
        user.keywords = json.dumps(data.get("keywords", []), ensure_ascii=False)
        user.blacklist = json.dumps(data.get("blacklist", []), ensure_ascii=False)
        user.cover_letter_template = data.get("cover_letter_template")
        user.portfolio_links = data.get("portfolio_links")

        if cv_file_id:
            user.cv_file_id = cv_file_id[:200]
        if cv_encrypted:
            user.cv_encrypted = cv_encrypted

        user.is_active = True
        await session.commit()
