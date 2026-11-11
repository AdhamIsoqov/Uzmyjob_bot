"""End-to-End (E2E) workflow integration test."""

import csv
import io
import json
from unittest.mock import MagicMock, patch

import pytest

from uzmyjob.adapters.hh_api import HeadHunterAdapter
from uzmyjob.agents.cover_letter import generate_cover_letter
from uzmyjob.agents.matcher import match_vacancy
from uzmyjob.pipeline.pipeline import JobPipeline
from uzmyjob.utils.crypto import decrypt_str, encrypt_str
from uzmyjob.utils.cv_parser import CVParser


@pytest.mark.asyncio
async def test_full_user_lifecycle_e2e():
    """To'liq foydalanuvchi sikli (Wizard -> CV -> Fetch -> Match -> Cover Letter -> CSV Export)."""
    user_profile = {
        "position": "Backend Developer",
        "city": "Toshkent",
        "experience_years": 3,
        "min_salary": 2000,
        "keywords": ["Python", "FastAPI", "PostgreSQL", "Docker"],
        "blacklist": ["стажировка", "amaliyot"],
    }

    sample_cv = """
    Dasturchi: Jasur
    Email: jasur.dev@uzmyjob.uz
    Tel: +998901234567
    Tajriba: Python, FastAPI, Docker, PostgreSQL bilan 3 yillik tajriba.
    """
    with patch.object(CVParser, "extract_text_from_pdf", return_value=sample_cv):
        cv_data = CVParser.parse_cv(b"mock_bytes", "resume.pdf")
        assert "python" in cv_data["detected_skills"]
        assert "fastapi" in cv_data["detected_skills"]

    encrypted_cv = encrypt_str(cv_data["text"])
    assert decrypt_str(encrypted_cv) == cv_data["text"]

    adapter = HeadHunterAdapter()
    raw_hh = {
        "id": "999888",
        "name": "Senior Python Developer (FastAPI)",
        "employer": {"name": "FinTech LLC"},
        "area": {"name": "Toshkent"},
        "salary": {"from": 2500, "to": 4000, "currency": "USD"},
        "snippet": {
            "requirement": "Python, FastAPI, Docker",
            "responsibility": "Yuqori yuklamali tizimlar",
        },
        "alternate_url": "https://hh.uz/vacancy/999888",
    }
    normalized_vac = adapter.normalize(raw_hh)
    assert normalized_vac["title"] == "Senior Python Developer (FastAPI)"
    assert normalized_vac["salary_min"] == 2500

    pipeline = JobPipeline()
    is_blocked = pipeline._is_blacklisted(
        normalized_vac["title"],
        normalized_vac["description"],
        user_profile["blacklist"],
    )
    assert is_blocked is False

    mock_matcher_response = MagicMock()
    mock_matcher_response.text = json.dumps({
        "match_score": 0.92,
        "reason": "Python, FastAPI va tajriba to'liq mos",
    })

    with patch("uzmyjob.agents.matcher.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_matcher_response
        mock_get_client.return_value = mock_client

        score, reason = await match_vacancy(user_profile, normalized_vac)
        assert score >= 0.90
        assert "FastAPI" in reason or "Python" in reason

    template = (
        "Salom! Men {{ company_name }} dagi {{ vacancy_title }} lavozimiga qiziqyapman. "
        "Tajriba: {{ years_exp }} yil."
    )
    mock_cl_response = MagicMock()
    mock_cl_response.text = (
        "Hurmatli FinTech LLC, Senior Python Developer lavozimiga rezyumeimni yo'llayapman."
    )

    with patch("uzmyjob.agents.cover_letter.get_client") as mock_cl_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_cl_response
        mock_cl_client.return_value = mock_client

        letter = await generate_cover_letter(template, normalized_vac, user_profile)
        assert len(letter) > 20
        assert "FinTech" in letter or "Python" in letter

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Manba", "Vakansiya", "Kompaniya", "Holati"])
    writer.writerow(["1", "hh", normalized_vac["title"], normalized_vac["company"], "sent"])
    csv_content = output.getvalue()

    assert "Senior Python Developer" in csv_content
    assert "FinTech LLC" in csv_content
