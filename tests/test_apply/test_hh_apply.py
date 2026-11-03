"""Unit tests for HeadHunterApplyService."""
from unittest.mock import AsyncMock, patch

import pytest

from uzmyjob.apply.hh_apply import HeadHunterApplyService


def test_authorization_url_generation():
    """OAuth avtorizatsiya havolasi to'g'ri shakllanishi."""
    service = HeadHunterApplyService(
        client_id="test_client_id",
        client_secret="test_secret",
        redirect_uri="https://t.me/Uzmyjob_bot",
    )
    url = service.get_authorization_url(state="12345")
    assert "https://hh.uz/oauth/authorize" in url
    assert "client_id=test_client_id" in url
    assert "state=12345" in url


@pytest.mark.asyncio
async def test_apply_success():
    """Vakansiyaga murojaat 201 Created qaytarsa True bo'lishi kerak."""
    service = HeadHunterApplyService(
        client_id="test_client_id",
        client_secret="test_secret",
    )

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 201
        mock_resp.headers = {"Location": "https://api.hh.uz/negotiations/999"}
        mock_post.return_value = mock_resp

        success, msg = await service.apply(
            access_token="valid_token",
            vacancy_id="12345",
            resume_id="res_777",
            message="Salom",
        )
        assert success is True
        assert "muvaffaqiyatli" in msg


@pytest.mark.asyncio
async def test_apply_already_applied():
    """Allaqachon topshirilgan bo'lsa to'g'ri ogohlantirish qaytishi kerak."""
    service = HeadHunterApplyService(
        client_id="test_client_id",
        client_secret="test_secret",
    )

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 400
        mock_resp.text = '{"errors": [{"value": "already_applied"}]}'
        mock_post.return_value = mock_resp

        success, msg = await service.apply(
            access_token="valid_token",
            vacancy_id="12345",
            resume_id="res_777",
        )
        assert success is False
        assert "allaqachon" in msg

