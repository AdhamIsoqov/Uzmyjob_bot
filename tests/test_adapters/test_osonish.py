"""Unit tests for OsonIshAdapter (osonish.uz)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uzmyjob.adapters.osonish import OsonIshAdapter


def test_osonish_normalize_api_payload():
    """osonish.uz JSON javobini to'liq normallashtirish."""
    adapter = OsonIshAdapter()
    raw = {
        "id": 73057,
        "title": "Backend Developer",
        "min_salary": 10000000,
        "max_salary": 15000000,
        "created_at": "2026-11-10T06:14:06.000000Z",
        "info": "<ul><li>Python</li><li>FastAPI</li></ul><p>Aloqa: hr@bank.uz</p>",
        "additional_phone": "+998",
        "another_network": "@bank_hr",
        "is_hidden_network": 0,
        "address": "Toshkent, Mirzo Ulug'bek",
        "company": {"id": 664, "name": "Orient Finans Bank AJ"},
        "filial": {"region": {"name_uz": "Toshkent shahri"}},
        "hr": {"fio": "HR Bo'lim", "phone": "+998946600686"},
        "skills_details": [{"skill_name": "PostgreSQL"}],
    }

    norm = adapter.normalize(raw)
    assert norm["source"] == "osonish"
    assert norm["external_id"] == "73057"
    assert norm["title"] == "Backend Developer"
    assert norm["company"] == "Orient Finans Bank AJ"
    assert norm["city"] == "Toshkent"
    assert norm["salary_min"] == 10_000_000
    assert norm["salary_max"] == 15_000_000
    assert norm["currency"] == "UZS"
    assert norm["url"] == "https://osonish.uz/vacancies/73057"
    assert norm["contact_phone"] == "+998946600686"
    assert norm["contact_telegram"] == "@bank_hr"
    assert norm["contact_email"] == "hr@bank.uz"
    assert "PostgreSQL" in norm["description"]
    assert "<li>" not in norm["description"]


@pytest.mark.asyncio
async def test_osonish_fetch_success_and_error():
    adapter = OsonIshAdapter(rate_limit_delay=0.0)
    mock_ok = MagicMock(status_code=200)
    mock_ok.json.return_value = {"success": True, "data": {"data": [{"id": 1, "title": "QA"}]}}
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_ok)):
        rows = await adapter.fetch(per_page=1)
        assert len(rows) == 1
        assert rows[0]["title"] == "QA"

    mock_err = MagicMock(status_code=500)
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_err)):
        assert await adapter.fetch() == []
