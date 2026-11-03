"""Unit tests for RSSFreelanceAdapter."""
from uzmyjob.adapters.rss import RSSFreelanceAdapter


def test_rss_normalize():
    """RSS itemini to'g'ri normallashtirish testi."""
    adapter = RSSFreelanceAdapter()
    raw = {
        "id": "task_1001",
        "url": "https://freelance.habr.com/tasks/1001",
        "title": "Telegram bot for job search",
        "description": "Python aiogram 3 va PostgreSQL kerak",
        "company": "Upwork Client",
    }

    norm = adapter.normalize(raw)
    assert norm["source"] == "freelance_rss"
    assert norm["external_id"] == "task_1001"
    assert norm["title"] == "Telegram bot for job search"
    assert norm["city"] == "Remote (Masofaviy)"
    assert norm["url"] == "https://freelance.habr.com/tasks/1001"
