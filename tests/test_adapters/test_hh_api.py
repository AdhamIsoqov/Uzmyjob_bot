"""Unit tests for HeadHunterAdapter."""
from unittest.mock import MagicMock, patch

import pytest

from uzmyjob.adapters.hh_api import HeadHunterAdapter


def test_hh_normalize():
    """hh.uz JSON formatini to'g'ri normallashtirish testi."""
    adapter = HeadHunterAdapter()
    raw = {
        "id": "123456",
        "name": "Python Senior Developer",
        "employer": {"name": "Tech Corp"},
        "area": {"name": "Toshkent"},
        "salary": {"from": 2000, "to": 3500, "currency": "USD"},
        "snippet": {
            "requirement": "Python, Django, FastAPI",
            "responsibility": "Mikroservislarni ishlab chiqish",
        },
        "alternate_url": "https://hh.uz/vacancy/123456",
        "contacts": {
            "phones": [{"country": "998", "city": "90", "number": "1234567"}],
            "email": "hr@techcorp.uz",
        },
        "published_at": "2026-11-04T10:00:00+05:00",
    }

    norm = adapter.normalize(raw)

    assert norm["source"] == "hh"
    assert norm["external_id"] == "123456"
    assert norm["title"] == "Python Senior Developer"
    assert norm["company"] == "Tech Corp"
    assert norm["city"] == "Toshkent"
    assert norm["salary_min"] == 2000
    assert norm["salary_max"] == 3500
    assert norm["currency"] == "USD"
    assert norm["contact_email"] == "hr@techcorp.uz"
    assert norm["contact_phone"] == "+998901234567"
    assert "FastAPI" in norm["description"]


@pytest.mark.asyncio
async def test_hh_fetch_success():
    """hh.uz fetch so'rovi muvaffaqiyatli bo'lganda elementlarni qaytarishi."""
    adapter = HeadHunterAdapter(rate_limit_delay=0.0)

    mock_response_data = {
        "items": [
            {"id": "1", "name": "Dev 1"},
            {"id": "2", "name": "Dev 2"},
        ]
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response_data
        mock_get.return_value = mock_resp

        items = await adapter.fetch(text="Python")
        assert len(items) == 2
        assert items[0]["name"] == "Dev 1"

