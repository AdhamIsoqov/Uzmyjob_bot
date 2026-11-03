"""Cover Letter Agent — Jinja2 + Gemini personalizatsiya."""
import json

from jinja2 import Template

from uzmyjob.agents.client import get_client
from uzmyjob.utils.logger import log

SYSTEM_INSTRUCTION = """Sen murojaat xabari yozuvchi agentisan.
Foydalanuvchi shabloni va vakansiya ma'lumoti beriladi.
Shablon o'zgaruvchilarini ({{ vacancy_title }}, {{ company_name }} va h.k.) to'ldirib,
professional va qisqa (150-200 so'z) murojaat xabari yoz.
Faqat tayyor xabarni qaytargin, boshqa hech narsa yo'q."""


async def generate_cover_letter(
    template_str: str,
    vacancy: dict,
    user_profile: dict,
) -> str:
    """
    Jinja2 shablon + Gemini LLM → personalized cover letter.
    """
    # 1-qadam: Jinja2 asosiy o'zgaruvchilarni to'ldirish
    try:
        tpl = Template(template_str)
        base_text = tpl.render(
            vacancy_title=vacancy.get("title", ""),
            company_name=vacancy.get("company", ""),
            position=user_profile.get("position", ""),
            city=vacancy.get("city", ""),
            years_exp=user_profile.get("experience_years", ""),
        )
    except Exception:
        base_text = template_str

    # 2-qadam: Gemini bilan personalizatsiya
    client = get_client()
    prompt = (
        f"Shablon asosida yozilgan xabar:\n{base_text}\n\n"
        f"Vakansiya tafsilotlari:\n{json.dumps(vacancy, ensure_ascii=False)}"
    )
    try:
        interaction = client.interactions.create(
            model="gemini-3.8-flash",
            system_instruction=SYSTEM_INSTRUCTION,
            input=prompt,
            store=False,
        )
        return interaction.output_text or base_text
    except Exception as e:
        log.error("cover_letter_error", error=str(e))
        return base_text
