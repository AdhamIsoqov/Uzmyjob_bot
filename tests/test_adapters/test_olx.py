"""Unit tests for OLXScraperAdapter."""
from uzmyjob.adapters.olx import OLXScraperAdapter


def test_olx_normalize():
    """OLX e'lonini to'g'ri normallashtirish."""
    adapter = OLXScraperAdapter()
    raw = {
        "id": "abc12345",
        "url": "https://www.olx.uz/d/obyavlenie/python-developer-IDabc12345.html",
        "title": "Python Backend Dasturchi",
        "company": "Smart Solutions",
        "city": "Toshkent",
        "salary_min": 10000000,
        "salary_max": 25000000,
        "currency": "UZS",
        "phone": "+998901234567",
        "telegram": "@smart_hr",
    }

    norm = adapter.normalize(raw)
    assert norm["source"] == "olx"
    assert norm["external_id"] == "abc12345"
    assert norm["title"] == "Python Backend Dasturchi"
    assert norm["city"] == "Toshkent"
    assert norm["salary_min"] == 10000000
    assert norm["contact_telegram"] == "@smart_hr"
    assert norm["contact_phone"] == "+998901234567"
