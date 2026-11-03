"""Foydalanuvchi profilini sozlash va rezyume yuklash uchun FSM Wizard."""
import json

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardRemove
from sqlalchemy import select

from uzmyjob.models.base import AsyncSessionLocal
from uzmyjob.models.user import User
from uzmyjob.utils.crypto import encrypt
from uzmyjob.utils.cv_parser import CVParser
from uzmyjob.utils.logger import log

router = Router()


class ProfileWizard(StatesGroup):
    position = State()
    city = State()
    experience = State()
    min_salary = State()
    keywords = State()
    blacklist = State()
    cv_upload = State()


@router.message(Command("wizard"))
@router.message(Command("profil"))
async def start_wizard(message: Message, state: FSMContext):
    """Wizard boshlanishi: Mutaxassislik so'rash."""
    await state.clear()
    await message.answer(
        "🎯 <b>Profil sozlash bosqichiga xush kelibsiz!</b>\n\n"
        "1-qadam: Qaysi <b>lavozim yoki mutaxassislik</b> bo'yicha ish qidiryapsiz?\n"
        "<i>(Masalan: Python Backend Developer, DevOps, Frontend React)</i>",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(ProfileWizard.position)


@router.message(ProfileWizard.position)
async def process_position(message: Message, state: FSMContext):
    """Mutaxassislik saqlandi, shahar so'rash."""
    await state.update_data(position=message.text.strip())
    await message.answer(
        "📍 2-qadam: Qaysi <b>shahar yoki format</b> ma'qul?\n"
        "<i>(Masalan: Toshkent, Samarqand yoki Remote / Masofaviy)</i>"
    )
    await state.set_state(ProfileWizard.city)


@router.message(ProfileWizard.city)
async def process_city(message: Message, state: FSMContext):
    """Shahar saqlandi, tajriba so'rash."""
    await state.update_data(city=message.text.strip())
    await message.answer(
        "⏳ 3-qadam: Necha yillik <b>ish tajribasiga</b> egasiz?\n"
        "<i>(Faqat son yozing, masalan: 2 yoki 4)</i>"
    )
    await state.set_state(ProfileWizard.experience)


@router.message(ProfileWizard.experience)
async def process_experience(message: Message, state: FSMContext):
    """Tajriba saqlandi, maosh so'rash."""
    try:
        years = int(re_digits(message.text))
    except Exception:
        years = 1
    await state.update_data(experience=years)
    await message.answer(
        "💰 4-qadam: Kutilayotgan <b>minimal maosh</b> qancha?\n"
        "<i>(Masalan: 1000 yoki 10000000)</i>"
    )
    await state.set_state(ProfileWizard.min_salary)


def re_digits(text: str) -> str:
    """Faqat raqamlarni ajratish."""
    import re
    digits = re.findall(r"\d+", text)
    return digits[0] if digits else "0"


@router.message(ProfileWizard.min_salary)
async def process_salary(message: Message, state: FSMContext):
    """Maosh saqlandi, kalit so'zlar so'rash."""
    try:
        sal = int(re_digits(message.text))
    except Exception:
        sal = 0
    await state.update_data(min_salary=sal)
    await message.answer(
        "🔑 5-qadam: Vakansiyalarda qidiriladigan <b>kalit so'zlar / texnologiyalarni</b> yozing:\n"
        "<i>(Vergul bilan ajrating, masalan: Python, FastAPI, Docker, PostgreSQL)</i>"
    )
    await state.set_state(ProfileWizard.keywords)


@router.message(ProfileWizard.keywords)
async def process_keywords(message: Message, state: FSMContext):
    """Kalit so'zlar saqlandi, qora ro'yxat so'rash."""
    raw_kw = [k.strip() for k in message.text.split(",") if k.strip()]
    await state.update_data(keywords=raw_kw)
    await message.answer(
        "🚫 6-qadam: <b>Qora ro'yxat (Blacklist)</b> — qaysi so'zlar bor vakansiyalarni ko'rsatmaylik?\n"
        "<i>(Masalan: стажировка, amaliyot, tarmoqli marketing, kazino)</i>"
    )
    await state.set_state(ProfileWizard.blacklist)


@router.message(ProfileWizard.blacklist)
async def process_blacklist(message: Message, state: FSMContext):
    """Blacklist saqlandi, CV fayl so'rash."""
    raw_bl = [b.strip() for b in message.text.split(",") if b.strip()]
    await state.update_data(blacklist=raw_bl)
    await message.answer(
        "📄 7-qadam: Oxirgi qadam — <b>Rezyumeingizni (CV) hujjat (document) ko'rinishida yuboring</b> (PDF yoki DOCX formatida).\n\n"
        "<i>(Agar rezyumeni hozir yuklamoqchi bo'lmasangiz, shunchaki /skip deb yozing)</i>"
    )
    await state.set_state(ProfileWizard.cv_upload)


@router.message(ProfileWizard.cv_upload, F.document)
async def process_cv_file(message: Message, state: FSMContext, bot: Bot):
    """CV faylini qabul qilish, tahlil qilish va shifrlash."""
    doc = message.document
    fname = doc.file_name or "resume.pdf"

    if not fname.lower().endswith((".pdf", ".docx", ".doc")):
        await message.answer("⚠️ Iltimos, faqat PDF yoki DOCX formatidagi fayl yuboring.")
        return

    await message.answer("⏳ Rezyume yuklanmoqda va tahlil qilinmoqda...")

    try:
        # Faylni yuklab olamiz
        file_io = await bot.download(doc.file_id)
        file_bytes = file_io.read()

        # CVParser orqali ma'lumotlarni o'qiymiz
        parsed_data = CVParser.parse_cv(file_bytes, fname)
        detected_skills = parsed_data.get("detected_skills", [])

        # AES-256 Fernet orqali faylni shifrlaymiz
        encrypted_bytes = encrypt(file_bytes)

        # Wizard ma'lumotlarini bazaga saqlaymiz
        data = await state.get_data()
        await _save_user_profile(
            telegram_id=message.from_user.id,
            data=data,
            cv_file_id=doc.file_id,
            cv_encrypted=encrypted_bytes,
        )

        skills_text = ", ".join(detected_skills) if detected_skills else "qo'shimcha ko'nikmalar"
        await message.answer(
            "✅ <b>Profil va Rezyume muvaffaqiyatli saqlandi!</b>\n\n"
            f"📄 Fayl: <b>{fname}</b>\n"
            f"💡 CV dan aniqlangan texnologiyalar: <i>{skills_text}</i>\n\n"
            "🔍 Endi bot sizning profilingiz bo'yicha eng mos vakansiyalarni avtomatik tarzda yetkazib turadi!"
        )
    except Exception as e:
        log.error("cv_upload_failed", error=str(e))
        await message.answer(f"❌ Faylni yuklashda xatolik yuz berdi: {e!s}")

    await state.clear()


@router.message(ProfileWizard.cv_upload, Command("skip"))
async def process_skip_cv(message: Message, state: FSMContext):
    """CV yuklashni o'tkazib yuborish."""
    data = await state.get_data()
    await _save_user_profile(
        telegram_id=message.from_user.id,
        data=data,
        cv_file_id=None,
        cv_encrypted=None,
    )
    await state.clear()
    await message.answer(
        "✅ <b>Profilingiz saqlandi!</b>\n\n"
        "Keyinroq rezyume yuklash uchun istalgan vaqt /wizard yoki /profil buyrug'ini bering."
    )


async def _save_user_profile(
    telegram_id: int,
    data: dict,
    cv_file_id: str | None,
    cv_encrypted: bytes | None,
):
    """Foydalanuvchi ma'lumotlarini PostgreSQL da saqlash."""
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(stmt)).scalar_one_or_none()

        if not user:
            user = User(telegram_id=telegram_id)
            session.add(user)

        user.position = data.get("position")
        user.city = data.get("city")
        user.experience_years = data.get("experience", 0)
        user.min_salary = data.get("min_salary", 0)
        user.keywords = json.dumps(data.get("keywords", []), ensure_ascii=False)
        user.blacklist = json.dumps(data.get("blacklist", []), ensure_ascii=False)

        if cv_file_id:
            user.cv_file_id = cv_file_id
        if cv_encrypted:
            user.cv_encrypted = cv_encrypted

        user.is_active = True
        await session.commit()
