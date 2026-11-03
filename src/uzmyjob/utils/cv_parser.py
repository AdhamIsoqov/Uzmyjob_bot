"""CV fayllarni (PDF va DOCX) o'qish va matnini ajratib olish moduli."""
import io
import re

import docx
import pdfplumber

from uzmyjob.utils.logger import log


class CVParser:
    """PDF va DOCX formatidagi rezyumelarni tahlil qilish va ma'lumotlarni ajratish."""

    @staticmethod
    def extract_text_from_pdf(file_bytes: bytes) -> str:
        """PDF baytlaridan matnni ajratib oladi."""
        text_parts = []
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            return "\n".join(text_parts).strip()
        except Exception as e:
            log.error("cv_pdf_parse_error", error=str(e))
            return ""

    @staticmethod
    def extract_text_from_docx(file_bytes: bytes) -> str:
        """DOCX baytlaridan matnni ajratib oladi."""
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            text_parts = [para.text for para in doc.paragraphs if para.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text.strip():
                            text_parts.append(cell.text.strip())
            return "\n".join(text_parts).strip()
        except Exception as e:
            log.error("cv_docx_parse_error", error=str(e))
            return ""

    @classmethod
    def parse_cv(cls, file_bytes: bytes, filename: str) -> dict[str, str | list[str]]:
        """
        CV fayl turini aniqlab matnni oladi va kontaktlar / kalit so'zlarni ajratadi.
        """
        fname = filename.lower()
        if fname.endswith(".pdf"):
            text = cls.extract_text_from_pdf(file_bytes)
        elif fname.endswith((".docx", ".doc")):
            text = cls.extract_text_from_docx(file_bytes)
        else:
            text = ""

        # Email topish
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
        email = email_match.group(0) if email_match else ""

        # Telefon topish
        phone_match = re.search(r"(\+?998[\d\s-]{9,}|[\+\d\s\(\)-]{10,})", text)
        phone = phone_match.group(0).strip() if phone_match else ""

        # Oddiy texnologik kalit so'zlarni qidirish
        common_tech = [
            "python", "django", "fastapi", "flask", "postgresql", "mysql", "redis",
            "docker", "kubernetes", "git", "linux", "rest api", "graphql", "celery",
            "javascript", "typescript", "react", "vue", "nodejs", "aws", "ci/cd"
        ]
        found_skills = [
            tech for tech in common_tech
            if re.search(rf"\b{re.escape(tech)}\b", text, re.IGNORECASE)
        ]

        return {
            "text": text,
            "email": email,
            "phone": phone,
            "detected_skills": found_skills,
        }
