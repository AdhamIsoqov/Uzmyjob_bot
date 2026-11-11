"""Unit tests for OLXScraperAdapter."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


def test_olx_parse_html_cards_and_json_ld():
    """OLX JSON-LD va karta HTML bloklaridan vakansiyalarni ajratish."""
    html_cards = """
    <div data-cy="l-card">
      <a href="/d/obyavlenie/fastapi-dev-IDxyz99.html"><h6>FastAPI Developer</h6></a>
      <p data-testid="ad-price">1 000 - 2 000 USD</p>
      <p data-testid="location-date">Ташкент - Bugun</p>
      <p>Murojaat: @olx_hr +998901112233</p>
    </div>
    """
    parsed = OLXScraperAdapter.parse_html(html_cards)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "xyz99"
    assert parsed[0]["title"] == "FastAPI Developer"
    assert parsed[0]["city"] == "Toshkent"
    assert parsed[0]["salary_min"] == 1000
    assert parsed[0]["salary_max"] == 2000
    assert parsed[0]["currency"] == "USD"
    assert parsed[0]["telegram"] == "@olx_hr"

    json_ld_html = """
    <script type="application/ld+json">
    {
      "@type": "JobPosting",
      "title": "DevOps Engineer",
      "url": "https://www.olx.uz/d/obyavlenie/devops-IDab12.html",
      "hiringOrganization": {"name": "CloudUZ"},
      "jobLocation": {"address": {"addressLocality": "Samarkand"}},
      "baseSalary": {"currency": "UZS", "value": {"minValue": 12000000, "maxValue": 18000000}},
      "description": "Docker, Kubernetes. Email: devops@clouduz.uz"
    }
    </script>
    """
    ld_parsed = OLXScraperAdapter.parse_html(json_ld_html)
    assert len(ld_parsed) == 1
    assert ld_parsed[0]["id"] == "ab12"
    assert ld_parsed[0]["company"] == "CloudUZ"
    assert ld_parsed[0]["city"] == "Samarqand"
    assert ld_parsed[0]["salary_min"] == 12_000_000
    assert ld_parsed[0]["email"] == "devops@clouduz.uz"


@pytest.mark.asyncio
async def test_olx_fetch_cloudfront_403_returns_empty():
    """CloudFront 403 WAF javobida xatolik ko'tarmasdan bo'sh ro'yxat qaytarishi kerak."""
    adapter = OLXScraperAdapter(rate_limit_delay=0.0)
    mock_resp = MagicMock(status_code=403, headers={"server": "CloudFront"}, text="Blocked")
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        assert await adapter.fetch() == []
