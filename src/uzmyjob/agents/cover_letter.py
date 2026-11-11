"""Cover Letter Agent — Sandboxed Jinja2 + Gemini personalizatsiya."""
import json
from pathlib import Path

from jinja2 import StrictUndefined, meta
from jinja2.sandbox import ImmutableSandboxedEnvironment

from uzmyjob.agents.client import generate_gemini_text, get_client
from uzmyjob.utils.logger import log

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
MAX_TEMPLATE_LENGTH = 4000
ALLOWED_TEMPLATE_VARS = {
    "vacancy_title",
    "company_name",
    "position",
    "city",
    "years_exp",
    "sender_name",
}

_SANDBOX_ENV = ImmutableSandboxedEnvironment(
    autoescape=False,
    undefined=StrictUndefined,
)

SYSTEM_INSTRUCTION = """Sen murojaat xabari yozuvchi agentisan.
Foydalanuvchi shabloni va vakansiya ma'lumoti beriladi.
Shablon o'zgaruvchilarini ({{ vacancy_title }}, {{ company_name }} va h.k.) to'ldirib,
professional va qisqa (150-200 so'z) murojaat xabari yoz.
Faqat tayyor xabarni qaytargin, boshqa hech narsa yo'q."""


def get_default_template(language: str = "uz") -> str:
    """Tilga mos standart Jinja2 shablonini qaytaradi."""
    lang = language.lower() if language else "uz"
    tpl_file = TEMPLATES_DIR / f"cover_letter_{lang}.jinja2"
    if not tpl_file.exists():
        tpl_file = TEMPLATES_DIR / "cover_letter_uz.jinja2"
    if tpl_file.exists():
        return tpl_file.read_text(encoding="utf-8")
    return (
        "Salom!\n"
        "{{ company_name }} kompaniyasidagi {{ vacancy_title }} lavozimiga murojaat qilyapman.\n"
        "Men {{ years_exp }} yillik tajribaga ega {{ position }} mutaxassisiman.\n"
        "CV va portfolioni ilova qildim."
    )


def validate_template(template_str: str) -> tuple[bool, str]:
    """
    Sandboxed Jinja2 shablon sintaksisini va ruxsat etilgan o'zgaruvchilarni tekshiradi.
    """
    if not template_str or not template_str.strip():
        return True, "Bo'sh shablon (standart shablon ishlatiladi)"
    if len(template_str) > MAX_TEMPLATE_LENGTH:
        return False, f"Shablon hajmi juda katta (maksimum {MAX_TEMPLATE_LENGTH} belgi)."
    if "{%" in template_str or "%}" in template_str or "{#" in template_str:
        return False, "Shablonda Jinja2 boshqaruv teglari ({% ... %}) ruxsat etilmaydi."

    try:
        parsed_content = _SANDBOX_ENV.parse(template_str)
        variables = meta.find_undeclared_variables(parsed_content)
        unknown_vars = variables - ALLOWED_TEMPLATE_VARS
        if unknown_vars:
            return (
                False,
                f"Ruxsat etilmagan o'zgaruvchilar: {', '.join(sorted(unknown_vars))}. "
                f"Ruxsat etilganlar: {', '.join(sorted(ALLOWED_TEMPLATE_VARS))}",
            )
        # Sandboxda test render sinovi
        tpl = _SANDBOX_ENV.from_string(template_str)
        tpl.render(**{v: "test" for v in ALLOWED_TEMPLATE_VARS})
        return True, f"Shablon to'g'ri. Parametrlar: {', '.join(sorted(variables)) if variables else 'yoq'}"
    except Exception as exc:
        return False, f"Shablon xatosi: {exc!s}"


async def generate_cover_letter(
    template_str: str,
    vacancy: dict,
    user_profile: dict,
) -> str:
    """Sandboxed Jinja2 shablon + Gemini LLM → personalized cover letter."""
    if not template_str or not template_str.strip():
        template_str = get_default_template(user_profile.get("language", "uz"))

    try:
        tpl = _SANDBOX_ENV.from_string(template_str[:MAX_TEMPLATE_LENGTH])
        base_text = tpl.render(
            vacancy_title=vacancy.get("title", ""),
            company_name=vacancy.get("company", ""),
            position=user_profile.get("position", ""),
            city=vacancy.get("city", ""),
            years_exp=user_profile.get("experience_years", ""),
            sender_name=user_profile.get("name", "Nomzod"),
        )
    except Exception as exc:
        log.warning("cover_letter_jinja_render_error", error=str(exc))
        base_text = get_default_template(user_profile.get("language", "uz"))

    try:
        prompt = (
            f"Shablon asosida yozilgan xabar:\n{base_text}\n\n"
            f"Vakansiya tafsilotlari:\n{json.dumps(vacancy, ensure_ascii=False)}"
        )
        generated = await generate_gemini_text(
            prompt=prompt,
            system_instruction=SYSTEM_INSTRUCTION,
            timeout=10.0,
            client=get_client(),
        )
        return (generated.strip() or base_text)[:3500]
    except Exception as exc:
        log.error("cover_letter_error", error=str(exc))
        return base_text[:3500]
