"""Unit tests for ContactApplyService."""
from unittest.mock import MagicMock, patch

from uzmyjob.apply.contact_apply import ContactApplyService


def test_format_telegram_link():
    """Telegram havola formatini tekshirish."""
    # Matnsiz havola
    link1 = ContactApplyService.format_telegram_link("@hr_specialist")
    assert link1 == "https://t.me/hr_specialist"

    # Tayyor xabar bilan havola
    link2 = ContactApplyService.format_telegram_link("hr_specialist", prefilled_text="Salom, ish bormi?")
    assert "https://t.me/hr_specialist?text=" in link2
    assert "Salom" in link2


def test_format_phone_link():
    """Telefon havolasini tekshirish."""
    phone_link = ContactApplyService.format_phone_link("+998 90 123-45-67")
    assert phone_link == "tel:+998901234567"


def test_send_email_application_no_smtp_configured():
    """SMTP sozlamalari yo'q bo'lsa ogohlantirish qaytishi kerak."""
    with patch("uzmyjob.apply.contact_apply.settings") as mock_settings:
        mock_settings.smtp_user = ""
        mock_settings.smtp_pass = ""

        success, msg = ContactApplyService.send_email_application(
            to_email="hr@company.com",
            subject="Resume",
            body="Cover letter matni",
        )
        assert success is False
        assert "SMTP sozlamalari" in msg


def test_send_email_application_success():
    """SMTP orqali muvaffaqiyatli yuborish."""
    with patch("uzmyjob.apply.contact_apply.settings") as mock_settings, \
         patch("smtplib.SMTP") as mock_smtp_cls:
        mock_settings.smtp_user = "sender@gmail.com"
        mock_settings.smtp_pass = "secret_pass"
        mock_settings.smtp_host = "smtp.gmail.com"
        mock_settings.smtp_port = 587

        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        success, msg = ContactApplyService.send_email_application(
            to_email="hr@company.com",
            subject="Python Dev Resume",
            body="Salom, mening CV ilovada.",
            cv_bytes=b"%PDF-1.4 dummy cv content",
            cv_filename="resume.pdf",
        )

        assert success is True
        assert "muvaffaqiyatli" in msg
        mock_smtp.send_message.assert_called_once()
