"""Matcher agent uchun unit testlar."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_match_vacancy_high_score():
    """Mos vakansiya uchun yuqori score qaytarilishi kerak."""
    mock_interaction = MagicMock()
    mock_interaction.output_text = '{"match_score": 0.85, "reason": "Python/Django mos"}'

    with patch("uzmyjob.agents.matcher.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.interactions.create.return_value = mock_interaction
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


@pytest.mark.asyncio
async def test_match_vacancy_error_returns_zero():
    """API xatosida 0.0 qaytarilishi kerak."""
    with patch("uzmyjob.agents.matcher.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.interactions.create.side_effect = Exception("API Error")
        mock_get_client.return_value = mock_client

        from uzmyjob.agents.matcher import match_vacancy

        score, _reason = await match_vacancy({}, {})
        assert score == 0.0
