"""Vakansiyalarga munosabat bildirish (apply, cover letter, save, dismiss) callback handlerlari."""

from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from uzmyjob.agents.cover_letter import generate_cover_letter
from uzmyjob.apply.contact_apply import ContactApplyService
from uzmyjob.apply.hh_apply import HeadHunterApplyService
from uzmyjob.config import settings
from uzmyjob.models.application import Application, AppStatus
from uzmyjob.models.base import AsyncSessionLocal
from uzmyjob.models.user import User
from uzmyjob.models.vacancy import Vacancy
from uzmyjob.pipeline.pipeline import JobPipeline
from uzmyjob.utils.crypto import decrypt_str
from uzmyjob.utils.logger import log

router = Router()


def _parse_vacancy_id(data: str | None) -> int | None:
    """Callback data dan vakansiya ID sini xavfsiz ajratib olish."""
    if not data or ":" not in data:
        return None
    try:
        return int(data.split(":", 1)[1])
    except ValueError:
        return None


async def _record_application(user_id: int, source: str, external_id: str, vacancy_id: int) -> bool:
    """Murojaatni DB ga yozish. Dublikat bo'lsa False qaytaradi (crash qilmaydi)."""
    async with AsyncSessionLocal() as session:
        app = Application(
            user_id=user_id,
            source=source,
            external_id=external_id,
            vacancy_id=vacancy_id,
            status=AppStatus.SENT,
        )
        session.add(app)
        try:
            await session.commit()
            return True
        except IntegrityError:
            await session.rollback()
            return False


@router.message(Command("vacancies"))
@router.message(Command("vakansiyalar"))
@router.message(F.text == "💼 Vakansiyalar")
async def cmd_vacancies(message: Message, bot: Bot):
    """Foydalanuvchiga so'nggi mos vakansiyalarni qidirib ko'rsatish."""
    if not message.from_user:
        return
    telegram_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        u_stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(u_stmt)).scalar_one_or_none()
        if not user or not user.position:
            await message.answer("⚠️ Avval /start yoki /wizard orqali profilingizni sozlang.")
            return

    await message.answer("🔍 <b>Baza tekshirilmoqda...</b> Sizga mos eng yaxshi takliflar saralanmoqda...")
    pipeline = JobPipeline(bot=bot)
    sent_count = await pipeline.backfill_for_user(telegram_id, limit=3)
    if sent_count > 0:
        await message.answer(f"✨ Yuqorida profilingizga mos <b>{sent_count} ta</b> vakansiya ko'rsatildi.")
    else:
        await message.answer(
            "ℹ️ Hozircha bazada profilingiz talablariga to'liq mos keluvchi yangi vakansiya topilmadi.\n\n"
            "💡 <i>Maslahat: /profil orqali minimal maosh yoki moslik foizini (threshold) biroz pasaytirib ko'rishingiz mumkin. "
            "Har 15 daqiqada yangi e'lonlar chiqqanda bot sizga avtomatik xabar yuboradi!</i>"
        )


@router.callback_query(F.data.startswith("apply:"))
async def callback_apply(query: CallbackQuery):
    """Vakansiyaga murojaat qilish tugmasi."""
    vacancy_id = _parse_vacancy_id(query.data)
    if vacancy_id is None:
        await query.answer("❌ Noto'g'ri so'rov.", show_alert=True)
        return

    telegram_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == telegram_id))
        ).scalar_one_or_none()
        vacancy = (
            await session.execute(select(Vacancy).where(Vacancy.id == vacancy_id))
        ).scalar_one_or_none()

        if not user or not vacancy:
            await query.answer(
                "⚠️ Bu vakansiya e'loni eskirgan yoki bazadan olib tashlangan.",
                show_alert=True,
            )
            return

        user_id = user.id
        user_position = user.position
        hh_access_token_enc = user.hh_access_token_enc
        hh_resume_id = user.hh_resume_id
        vac_id = vacancy.id
        vac_source = vacancy.source
        vac_external_id = vacancy.external_id
        vac_title = vacancy.title
        vac_url = vacancy.url
        contact_telegram = vacancy.contact_telegram
        contact_phone = vacancy.contact_phone
        contact_email = vacancy.contact_email

    if vac_source == "hh":
        if not hh_access_token_enc or not hh_resume_id:
            auth_service = HeadHunterApplyService(
                client_id=settings.hh_client_id,
                client_secret=settings.hh_client_secret,
            )
            auth_url = escape(auth_service.get_authorization_url(state=str(telegram_id)))
            if query.message:
                await query.message.reply(
                    "⚠️ <b>hh.uz hisobingiz ulanmagan yoki rezyume tanlanmagan.</b>\n\n"
                    f"1. <a href='{auth_url}'>Bu havola orqali ruxsat bering</a>\n"
                    "2. Keyin chiqqan kodni <code>/hh_code SIZNING_KODINGIZ</code> ko'rinishida yuboring.",
                    disable_web_page_preview=True,
                )
            await query.answer()
            return

        access_token = decrypt_str(hh_access_token_enc)
        hh_service = HeadHunterApplyService(
            client_id=settings.hh_client_id,
            client_secret=settings.hh_client_secret,
        )

        success, msg = await hh_service.apply(
            access_token=access_token,
            vacancy_id=vac_external_id,
            resume_id=hh_resume_id,
            message="",
        )

        if success:
            created = await _record_application(user_id, vac_source, vac_external_id, vac_id)
            alert_text = (
                "✅ Murojaat muvaffaqiyatli yuborildi!"
                if created
                else "ℹ️ Siz bu vakansiyaga allaqachon murojaat qilgansiz."
            )
            await query.answer(alert_text, show_alert=True)
            if query.message:
                try:
                    await query.message.edit_reply_markup(reply_markup=None)
                except Exception as e:
                    log.debug("edit_reply_markup_skipped", error=str(e))
        else:
            await query.answer(f"❌ {msg}", show_alert=True)
        return

    contacts = []
    buttons = []

    user_title = user_position or "mutaxassis"
    prefilled_msg = (
        f"Assalomu alaykum! Men {vac_title} vakansiyasi bo'yicha murojaat qilmoqdaman. "
        f"Men {user_title}man."
    )

    if contact_telegram:
        tg_link = ContactApplyService.format_telegram_link(
            contact_telegram, prefilled_text=prefilled_msg
        )
        contacts.append(f"✈️ <b>Telegram:</b> {escape(contact_telegram)}")
        buttons.append(
            [
                InlineKeyboardButton(
                    text="✈️ Telegramda yozish (tayyor xabar)",
                    url=tg_link,
                )
            ]
        )

    if contact_phone:
        contacts.append(f"📞 <b>Tel:</b> {escape(contact_phone)}")

    if contact_email:
        contacts.append(f"📧 <b>Email:</b> {escape(contact_email)}")

    contact_text = (
        "\n".join(contacts) if contacts else "To'g'ridan-to'g'ri kontakt ko'rsatilmagan."
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

    created = await _record_application(user_id, vac_source, vac_external_id, vac_id)

    if query.message:
        source_link_html = (
            f"🔗 <a href='{escape(vac_url)}'><b>Asl e'lonni ochish ↗</b></a>"
            if vac_url
            else ""
        )
        await query.message.reply(
            f"📝 <b>Murojaat uchun kontaktlar:</b>\n\n{contact_text}\n\n{source_link_html}",
            reply_markup=reply_markup,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    await query.answer(
        "Kontaktlar chiqarildi!" if created else "Kontaktlar avval ham ochilgan.",
    )


@router.callback_query(F.data.startswith("cover:"))
async def callback_cover(query: CallbackQuery):
    """Murojaat xabari (cover letter) tayyorlash."""
    vacancy_id = _parse_vacancy_id(query.data)
    if vacancy_id is None:
        await query.answer("❌ Noto'g'ri so'rov.", show_alert=True)
        return

    telegram_id = query.from_user.id
    await query.answer("Cover letter tayyorlanmoqda...")

    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == telegram_id))
        ).scalar_one_or_none()
        vacancy = (
            await session.execute(select(Vacancy).where(Vacancy.id == vacancy_id))
        ).scalar_one_or_none()

        if not user or not vacancy:
            if query.message:
                await query.message.reply(
                    "⚠️ <b>Bu vakansiya e'loni eskirgan yoki bazadan yangilangani sababli topilmadi.</b>\n\n"
                    "Sizga mos yangi takliflarni ko'rish uchun /vacancies buyrug'ini yuboring.",
                    parse_mode="HTML",
                )
            return

        template_str = user.cover_letter_template or (
            "Salom! Men {{ company_name }} dagi {{ vacancy_title }} lavozimiga qiziqish bildiryapman. "
            "Tajribam: {{ years_exp }} yil."
        )
        user_profile = {
            "position": user.position or "",
            "skills": user.skills or [],
            "experience_years": user.experience_years or 0,
        }
        vacancy_dict = {
            "title": vacancy.title,
            "company": vacancy.company or "",
            "city": vacancy.city or "",
            "description": vacancy.description or "",
        }

    letter = await generate_cover_letter(template_str, vacancy_dict, user_profile)

    if query.message:
        await query.message.reply(
            f"✉️ <b>Tayyorlangan murojaat xabari:</b>\n\n"
            f"<blockquote>{escape(letter)}</blockquote>\n\n"
            f"<i>Buni nusxalab olib, ish beruvchiga yuborishingiz mumkin.</i>",
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("save:"))
async def callback_save(query: CallbackQuery):
    """Vakansiyani chatda saqlangan sifatida belgilash."""
    if query.message and query.message.reply_markup:
        new_rows: list[list[InlineKeyboardButton]] = []
        for row in query.message.reply_markup.inline_keyboard:
            new_row = []
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("save:"):
                    new_row.append(
                        InlineKeyboardButton(text="✅ Saqlandi", callback_data="saved:done")
                    )
                else:
                    new_row.append(btn)
            new_rows.append(new_row)
        try:
            await query.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(inline_keyboard=new_rows)
            )
        except Exception as e:
            log.debug("save_markup_update_skipped", error=str(e))
    await query.answer("🔖 Vakansiya ushbu chatda saqlangan deb belgilandi.", show_alert=False)


@router.callback_query(F.data == "saved:done")
async def callback_saved_done(query: CallbackQuery):
    """Allaqachon saqlangan vakansiya tugmasi."""
    await query.answer("🔖 Bu vakansiya allaqachon saqlangan.", show_alert=False)


@router.callback_query(F.data.startswith("dismiss:"))
async def callback_dismiss(query: CallbackQuery):
    """Vakansiya e'lonini yashirish (xavfsiz o'chirish yoki tugmalarni olib tashlash)."""
    if query.message:
        try:
            await query.message.delete()
        except Exception:
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception as e:
                log.debug("dismiss_cleanup_skipped", error=str(e))
    await query.answer("Vakansiya yashirildi.")
