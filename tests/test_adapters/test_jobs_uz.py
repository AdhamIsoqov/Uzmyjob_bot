"""Unit tests for JobsUzScraperAdapter (uzjobs.uz RSS) and parsing helpers."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uzmyjob.adapters._parsing import parse_salary_text
from uzmyjob.adapters.jobs_uz import JobsUzScraperAdapter


def test_jobs_uz_normalize():
    """jobs_uz e'lonini to'g'ri normallashtirish (backward compatibility)."""
    adapter = JobsUzScraperAdapter()
    raw = {
        "id": "778899",
        "url": "https://jobs.uz/ru/vacancies/view/778899",
        "title": "Django Backend Muhandis",
        "company": "IT Hub",
        "city": "Samarqand",
        "salary_min": 1500,
        "salary_max": 2500,
        "currency": "USD",
        "email": "jobs@ithub.uz",
    }

    norm = adapter.normalize(raw)
    assert norm["source"] == "jobs_uz"
    assert norm["external_id"] == "778899"
    assert norm["title"] == "Django Backend Muhandis"
    assert norm["city"] == "Samarqand"
    assert norm["salary_min"] == 1500
    assert norm["currency"] == "USD"
    assert norm["contact_email"] == "jobs@ithub.uz"


def test_jobs_uz_parse_windows1251_rss():
    """windows-1251 RSS XML dan rus va ingliz e'lonlari maosh va kompaniyasi bilan o'qiladi."""
    xml_str = """<?xml version="1.0" encoding="windows-1251"?>
<rss version="2.0"><channel>
  <item>
    <guid>http://uzjobs.uz/r/vakansy_view-34068.html</guid>
    <title><![CDATA[Вакансия: IT Специалист (Microsoft)]]></title>
    <description><![CDATA[Компания: OOO GRANT THORNTON<br><br>Регион: Ташкент<br><br>Предлагаемая зарплата: от 15 000 000 сум<br><br>Aloqa: hr@grant.uz]]></description>
    <link>https://uzjobs.uz/r/vakansy_view-34068.html</link>
    <pubDate>Wed, 11 Nov 2026 17:40:28 +0500</pubDate>
  </item>
  <item>
    <guid>http://uzjobs.uz/e/vakansy_view-34079.html</guid>
    <title><![CDATA[Vacancy: Junior Advisor(Expert) ]]></title>
    <description><![CDATA[Company: GIZ<br><br>Region: Tashkent<br><br>Salary offered: 375 У.Е (Брутто) в месяц (25 часов в неделю)]]></description>
    <link>https://uzjobs.uz/e/vakansy_view-34079.html</link>
    <pubDate>Tue, 10 Nov 2026 17:18:13 +0500</pubDate>
  </item>
</channel></rss>"""
    items = JobsUzScraperAdapter.parse_rss(xml_str.encode("cp1251"))
    assert len(items) == 2

    first = JobsUzScraperAdapter().normalize(items[0])
    assert first["external_id"] == "34068"
    assert first["title"] == "IT Специалист (Microsoft)"
    assert first["company"] == "OOO GRANT THORNTON"
    assert first["city"] == "Toshkent"
    assert first["salary_min"] == 15_000_000
    assert first["salary_max"] is None
    assert first["currency"] == "UZS"
    assert first["contact_email"] == "hr@grant.uz"

    second = JobsUzScraperAdapter().normalize(items[1])
    assert second["external_id"] == "34079"
    assert second["company"] == "GIZ"
    assert second["city"] == "Toshkent"
    assert second["salary_min"] == 375
    assert second["salary_max"] == 375
    assert second["currency"] == "USD"


def test_parse_salary_text_variants():
    assert parse_salary_text("5 000 000 - 10 000 000 сум") == (5_000_000, 10_000_000, "UZS")
    assert parse_salary_text("По итогам собеседования") == (None, None, None)


@pytest.mark.asyncio
async def test_jobs_uz_fetch_handles_http_error():
    adapter = JobsUzScraperAdapter(rate_limit_delay=0.0)
    mock_resp = MagicMock(status_code=503, content=b"")
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        assert await adapter.fetch() == []
