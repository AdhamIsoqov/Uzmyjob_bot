"""Kontaktlar (Telegram, Email, Telefon) orqali murojaat qilish xizmati."""
import email.message
import smtplib
import urllib.parse

from uzmyjob.config import settings
from uzmyjob.utils.logger import log


class ContactApplyService:
    """OLX, jobs.uz va Telegram kanallaridagi vakansiyalarga to'g'ridan-to'g'ri murojaat qilish."""

    @staticmethod
    def format_telegram_link(telegram_username: str, prefilled_text: str = "") -> str:
        """Ish beruvchining Telegram profiliga tayyor xabar bilan havola."""
        clean_user = telegram_username.lstrip("@")
        if prefilled_text:
            encoded_text = urllib.parse.quote(prefilled_text)
            return f"https://t.me/{clean_user}?text={encoded_text}"
        return f"https://t.me/{clean_user}"

    @staticmethod
    def format_phone_link(phone: str) -> str:
        """Telefon qo'ng'irog'i havolasi."""
        clean_phone = phone.replace(" ", "").replace("-", "")
        return f"tel:{clean_phone}"

    @staticmethod
    def send_email_application(
        to_email: str,
        subject: str,
        body: str,
        cv_bytes: bytes | None = None,
        cv_filename: str = "CV.pdf",
    ) -> tuple[bool, str]:
        """
        SMTP orqali ish beruvchiga cover letter va CV ni yuborish.
        Returns: (success, message)
        """
        if not settings.smtp_user or not settings.smtp_pass:
            return False, "SMTP sozlamalari (SMTP_USER/SMTP_PASS) kiritilmagan."

        try:
            msg = email.message.EmailMessage()
            msg["Subject"] = subject
            msg["From"] = settings.smtp_user
            msg["To"] = to_email
            msg.set_content(body)

            if cv_bytes:
                msg.add_attachment(
                    cv_bytes,
                    maintype="application",
                    subtype="pdf",
                    filename=cv_filename,
                )

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_pass)
                server.send_message(msg)

            log.info("email_application_sent", to=to_email)
            return True, "CV va xabar email orqali muvaffaqiyatli yuborildi!"

        except Exception as e:
            log.error("email_send_failed", to=to_email, error=str(e))
            return False, f"Email yuborishda xatolik: {e!s}"
