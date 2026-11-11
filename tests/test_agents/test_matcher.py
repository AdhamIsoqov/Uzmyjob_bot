"""Matcher agent uchun unit testlar."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_match_vacancy_high_score():
    """Chegaraviy L1 sohada Gemini L2 balli qaytarilishi kerak."""
    mock_response = MagicMock()
    mock_response.text = '{"match_score": 0.85, "reason": "Python/Django mos"}'

    with patch("uzmyjob.agents.matcher.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        from uzmyjob.agents.matcher import match_vacancy

        user_profile = {
            "position": "Backend Developer",
            "keywords": ["Python", "Django"],
            "min_salary": 1000,
        }
        vacancy = {
            "title": "Python/Django Backend Developer",
            "external_id": "test-001",
            "company": "Test Corp",
        }

        score, reason = await match_vacancy(user_profile, vacancy)
        assert score == 0.85
        assert "Python" in reason or "Django" in reason
        mock_client.models.generate_content.assert_called_once()


@pytest.mark.asyncio
async def test_match_vacancy_error_returns_zero():
    """Bo'sh profil/vakansiyada 0.0 qaytarilishi kerak."""
    from uzmyjob.agents.matcher import match_vacancy

    score, _reason = await match_vacancy({}, {})
    assert score == 0.0


@pytest.mark.asyncio
async def test_match_vacancy_api_error_uses_l1_fallback():
    """Gemini API xatosida L1 fallback balli qaytarilishi kerak."""
    with patch("uzmyjob.agents.matcher.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("API Error")
        mock_get_client.return_value = mock_client

        from uzmyjob.agents.matcher import compute_l1_score, match_vacancy

        user_profile = {
            "position": "Backend Developer",
            "keywords": ["Python", "Django"],
        }
        vacancy = {
            "title": "Python/Django Backend Developer",
            "external_id": "test-002",
        }
        expected_l1, _ = compute_l1_score(user_profile, vacancy)

        score, reason = await match_vacancy(user_profile, vacancy)
        assert score == expected_l1
        assert "L1 fallback" in reason
