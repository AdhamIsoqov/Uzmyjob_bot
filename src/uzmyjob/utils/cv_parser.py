"""CV fayllarni (PDF va DOCX) o'qish va matnini ajratib olish moduli."""
import io
import re
from typing import Any

import docx
import pdfplumber

from uzmyjob.utils.logger import log

COMMON_TECH_SKILLS = [
    "python", "django", "fastapi", "flask", "postgresql", "mysql", "sqlite",
    "redis", "mongodb", "elasticsearch", "docker", "kubernetes", "git", "linux",
    "rest api", "graphql", "grpc", "celery", "rabbitmq", "kafka",
    "javascript", "typescript", "react", "vue", "angular", "next.js", "nextjs",
    "nodejs", "nest.js", "nestjs", "express", "aws", "gcp", "azure", "ci/cd",
    "golang", "go", "java", "spring", "spring boot", "c#", ".net", "php",
    "laravel", "symfony", "flutter", "dart", "kotlin", "swift", "rust",
    "tailwind", "bootstrap", "html", "css", "redux", "microservices",
]


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
        except Exception as exc:
            log.error("cv_pdf_parse_error", error=str(exc))
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
        except Exception as exc:
            log.error("cv_docx_parse_error", error=str(exc))
            return ""

    @classmethod
    def parse_cv(cls, file_bytes: bytes, filename: str) -> dict[str, Any]:
        """CV fayl turini aniqlab matnni oladi va kontaktlar/ko'nikmalarni ajratadi."""
        fname = filename.lower()
        if fname.endswith(".doc"):
            raise ValueError("Eski .doc formati qo'llab-quvvatlanmaydi. Iltimos, PDF yoki DOCX yuboring.")

        if fname.endswith(".pdf"):
            text = cls.extract_text_from_pdf(file_bytes)
        elif fname.endswith(".docx"):
            text = cls.extract_text_from_docx(file_bytes)
        elif fname.endswith(".txt"):
            try:
                text = file_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("TXT fayl UTF-8 formatida bo'lishi kerak.") from exc
        else:
            raise ValueError("Qo'llab-quvvatlanmaydigan fayl formati. Faqat PDF, DOCX yoki TXT yuboring.")

        if not text.strip():
            raise ValueError("Fayldan matn ajratib bo'lmadi (skaner rasm yoki buzilgan fayl).")

        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
        email = email_match.group(0) if email_match else ""

        phone_match = re.search(r"(\+?998[\d\s-]{9,}|[\+\d\s\(\)-]{10,})", text)
        phone = phone_match.group(0).strip() if phone_match else ""

        tg_match = re.search(r"(?:@|(?:https?:\/\/)?t\.me\/)([a-zA-Z0-9_]{5,32})", text)
        telegram = f"@{tg_match.group(1)}" if tg_match else ""

        github_match = re.search(
            r"https?:\/\/(?:www\.)?github\.com\/[a-zA-Z0-9_-]+", text, re.IGNORECASE
        )
        github = github_match.group(0) if github_match else ""

        linkedin_match = re.search(
            r"https?:\/\/(?:www\.)?linkedin\.com\/in\/[a-zA-Z0-9_-]+", text, re.IGNORECASE
        )
        linkedin = linkedin_match.group(0) if linkedin_match else ""

        exp_match = re.search(
            r"(\d{1,2})\+?\s*(?:yil|yillik|year|years|let|goda?|лет|года?)\b"
            r"(?:\s+(?:tajriba|experience|staj|стаж|opit|опыт))?",
            text,
            re.IGNORECASE,
        )
        experience_years = int(exp_match.group(1)) if exp_match else None

        found_skills: list[str] = []
        for tech in COMMON_TECH_SKILLS:
            pattern = rf"(?<!\w){re.escape(tech)}(?!\w)"
            if re.search(pattern, text, re.IGNORECASE) and tech not in found_skills:
                found_skills.append(tech)

        return {
            "text": text,
            "email": email,
            "phone": phone,
            "telegram": telegram,
            "github": github,
            "linkedin": linkedin,
            "detected_skills": found_skills,
            "experience_years": experience_years,
        }
