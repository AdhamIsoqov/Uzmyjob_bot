"""Unit tests for CVParser."""
from unittest.mock import patch

from uzmyjob.utils.cv_parser import CVParser


def test_cv_skills_and_contacts_detection():
    """Matndan texnologiyalar va kontaktlarni ajratish testi."""
    sample_cv = """
    Ali Valiyev
    Email: ali.dev@gmail.com
    Tel: +998901234567

    Tajriba:
    Backend muhandis. Python, Django, FastAPI va PostgreSQL yordamida
    mikroservislar yaratganman. Docker va Git bilan muntazam ishlayman.
    """

    with patch.object(CVParser, "extract_text_from_pdf", return_value=sample_cv):
        result = CVParser.parse_cv(b"fake_pdf_bytes", "resume.pdf")

        assert result["email"] == "ali.dev@gmail.com"
        assert result["phone"] == "+998901234567"

        skills = result["detected_skills"]
        assert "python" in skills
        assert "fastapi" in skills
        assert "postgresql" in skills
        assert "docker" in skills
        assert "git" in skills
