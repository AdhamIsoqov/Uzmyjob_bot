"""Vacancy Matcher Agent — gemini-3.8-flash bilan."""
import json

from uzmyjob.agents.client import get_client
from uzmyjob.utils.logger import log

SYSTEM_INSTRUCTION = """Sen vakansiya filtrlash agentisan.
Foydalanuvchi profili va vakansiya ma'lumoti beriladi.
0.0–1.0 orasida match_score va qisqa izoh qaytarasan.
Javob faqat JSON formatida bo'lsin:
{"match_score": 0.75, "reason": "Python/Django talab qilinadi, tajriba mos"}

Qoidalar:
- blacklist so'zlar bo'lsa: score 0.0
- Kalit so'zlar to'liq mos: score 0.85+
- Shahar/remote mos bo'lmasa: score 0.3
- Maosh minimal dan past bo'lsa: score 0.4"""


async def match_vacancy(user_profile: dict, vacancy: dict) -> tuple[float, str]:
    """
    Vakansiyani foydalanuvchi profiliga moslashtiradi.
    Returns: (match_score, reason)
    """
    client = get_client()
    prompt = (
        f"Foydalanuvchi profili:\n{json.dumps(user_profile, ensure_ascii=False)}\n\n"
        f"Vakansiya:\n{json.dumps(vacancy, ensure_ascii=False)}"
    )
    try:
        interaction = client.interactions.create(
            model="gemini-3.8-flash",
            system_instruction=SYSTEM_INSTRUCTION,
            input=prompt,
            store=False,
        )
        result = json.loads(interaction.output_text or "{}")
        score = float(result.get("match_score", 0.0))
        reason = result.get("reason", "")
        log.info("vacancy_matched", score=score, vacancy_id=vacancy.get("external_id"))
        return score, reason
    except Exception as e:
        log.error("matcher_error", error=str(e))
        return 0.0, "Xatolik yuz berdi"
