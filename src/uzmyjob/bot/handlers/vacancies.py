"""Vakansiyalarga munosabat bildirish (apply, cover letter, save, dismiss) callback handlerlari."""
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

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

router = Router()


@router.message(Command("vacancies"))
@router.message(Command("vakansiyalar"))
@router.message(F.text == "💼 Vakansiyalar")
async def cmd_vacancies(message: Message, bot: Bot):
    """Foydalanuvchiga so'nggi mos vakansiyalarni qidirib ko'rsatish."""
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
    vacancy_id = int(query.data.split(":")[1])
    telegram_id = query.from_user.id

    async with AsyncSessionLocal() as session:
        # User va Vacancy ni topamiz
        u_stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(u_stmt)).scalar_one_or_none()

        v_stmt = select(Vacancy).where(Vacancy.id == vacancy_id)
        vacancy = (await session.execute(v_stmt)).scalar_one_or_none()

        if not user or not vacancy:
            await query.answer("⚠️ Bu vakansiya e'loni eskirgan yoki bazadan olib tashlangan.", show_alert=True)
            return

        # hh.uz auto-apply
        if vacancy.source == "hh":
            if not user.hh_access_token_enc or not user.hh_resume_id:
                auth_service = HeadHunterApplyService(
                    client_id=settings.hh_client_id,
                    client_secret=settings.hh_client_secret,
                )
                auth_url = auth_service.get_authorization_url(state=str(telegram_id))
                await query.message.reply(
                    "⚠️ <b>hh.uz hisobingiz ulanmagan yoki rezyume tanlanmagan.</b>\n\n"
                    f"1. <a href='{auth_url}'>Bu havola orqali ruxsat bering</a>\n"
                    "2. Keyin chiqqan kodni <code>/hh_code SIZNING_KODINGIZ</code> ko'rinishida yuboring.",
                    disable_web_page_preview=True,
                )
                await query.answer()
                return

            # Tokenni dehidratsiya (decrypt) qilamiz
            access_token = decrypt_str(user.hh_access_token_enc)
            hh_service = HeadHunterApplyService(
                client_id=settings.hh_client_id,
                client_secret=settings.hh_client_secret,
            )

            success, msg = await hh_service.apply(
                access_token=access_token,
                vacancy_id=vacancy.external_id,
                resume_id=user.hh_resume_id,
                message="",
            )

            if success:
                # DB'da application saqlaymiz
                app = Application(
                    user_id=user.id,
                    source=vacancy.source,
                    external_id=vacancy.external_id,
                    vacancy_id=vacancy.id,
                    status=AppStatus.SENT,
                )
                session.add(app)
                await session.commit()

                await query.answer("✅ Murojaat muvaffaqiyatli yuborildi!", show_alert=True)
                await query.message.edit_reply_markup(reply_markup=None)
            else:
                await query.answer(f"❌ {msg}", show_alert=True)

        else:
            # OLX, jobs.uz va Telegram kanallari uchun kontaktlar
            contacts = []
            buttons = []

            # Foydalanuvchi uchun tayyor qisqa murojaat xabari
            user_title = user.position or "mutaxassis"
            prefilled_msg = (
                f"Assalomu alaykum! Men {vacancy.title} vakansiyasi bo'yicha murojaat qilmoqdaman. "
                f"Men {user_title}man."
            )

            if vacancy.contact_telegram:
                tg_link = ContactApplyService.format_telegram_link(
                    vacancy.contact_telegram, prefilled_text=prefilled_msg
                )
                contacts.append(f"✈️ <b>Telegram:</b> {vacancy.contact_telegram}")
                buttons.append(
                    [
                        InlineKeyboardButton(
                            text="✈️ Telegramda yozish (tayyor xabar)",
                            url=tg_link,
                        )
                    ]
                )

            if vacancy.contact_phone:
                contacts.append(f"📞 <b>Tel:</b> {vacancy.contact_phone}")

            if vacancy.contact_email:
                contacts.append(f"📧 <b>Email:</b> {vacancy.contact_email}")

            contact_text = "\n".join(contacts) if contacts else "To'g'ridan-to'g'ri kontakt ko'rsatilmagan."

            reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

            # DB'da application saqlaymiz (kontakt ko'rildi / murojaat qilindi)
            app = Application(
                user_id=user.id,
                source=vacancy.source,
                external_id=vacancy.external_id,
                vacancy_id=vacancy.id,
                status=AppStatus.SENT,
            )
            session.add(app)
            await session.commit()

            await query.message.reply(
                f"📝 <b>Murojaat uchun kontaktlar:</b>\n\n{contact_text}\n\n"
                f"🔗 <a href='{vacancy.url}'><b>Telegramdagi asl postni ochish ↗</b></a>",
                reply_markup=reply_markup,
                parse_mode="HTML",
                disable_web_page_preview=False,
            )
            await query.answer("Kontaktlar chiqarildi!")


@router.callback_query(F.data.startswith("cover:"))
async def callback_cover(query: CallbackQuery):
    """Murojaat xabari (cover letter) tayyorlash."""
    vacancy_id = int(query.data.split(":")[1])
    telegram_id = query.from_user.id

    await query.answer("Cover letter tayyorlanmoqda...")

    async with AsyncSessionLocal() as session:
        u_stmt = select(User).where(User.telegram_id == telegram_id)
        user = (await session.execute(u_stmt)).scalar_one_or_none()

        v_stmt = select(Vacancy).where(Vacancy.id == vacancy_id)
        vacancy = (await session.execute(v_stmt)).scalar_one_or_none()

        if not user or not vacancy:
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
            "experience_years": user.experience_years or 0,
        }
        vacancy_dict = {
            "title": vacancy.title,
            "company": vacancy.company or "",
            "city": vacancy.city or "",
            "description": vacancy.description or "",
        }

        # Gemini Agent orqali cover letter yaratamiz
        letter = await generate_cover_letter(template_str, vacancy_dict, user_profile)

        await query.message.reply(
            f"✉️ <b>Tayyorlangan murojaat xabari:</b>\n\n"
            f"<blockquote>{letter}</blockquote>\n\n"
            f"<i>Buni nusxalab olib, ish beruvchiga yuborishingiz mumkin.</i>",
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("save:"))
async def callback_save(query: CallbackQuery):
    """Vakansiyani saqlab qo'yish."""
    await query.answer("🔖 Vakansiya saqlanganlar ro'yxatiga qo'shildi.", show_alert=True)


@router.callback_query(F.data.startswith("dismiss:"))
async def callback_dismiss(query: CallbackQuery):
    """Vakansiya xabarini yopish."""
    await query.message.delete()
    await query.answer("Rad etildi.")

