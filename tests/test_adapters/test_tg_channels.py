"""Unit tests for TelegramChannelAdapter."""
from uzmyjob.adapters.tg_channels import TelegramChannelAdapter


def test_tg_channel_normalize():
    """Telegram kanal postini to'g'ri normallashtirish."""
    adapter = TelegramChannelAdapter()
    raw = {
        "id": "UstozShogird/54321",
        "channel": "UstozShogird",
        "url": "https://t.me/UstozShogird/54321",
        "title": "Ish joyi: Python Backend mutaxassisi kerak",
        "description": "Talablar: Python, PostgreSQL, aiogram\nBog'lanish: @hr_uzb yoki +998901112233",
        "telegram": "@hr_uzb",
        "phone": "+998901112233",
    }

    norm = adapter.normalize(raw)
    assert norm["source"] == "tg_channel"
    assert norm["external_id"] == "UstozShogird/54321"
    assert norm["contact_telegram"] == "@hr_uzb"
    assert norm["contact_phone"] == "+998901112233"
    assert "Telegram: @UstozShogird" in norm["company"]
