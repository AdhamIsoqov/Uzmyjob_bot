"""L2 Gemini Flash Re-ranker — faqat 0.40–0.55 threshold orasidagi vakansiyalar uchun."""
import json

from uzmyjob.agents.client import get_client
from uzmyjob.utils.logger import log

SYSTEM_INSTRUCTION = """Sen vakansiya re-ranklash agentisan.
Bir nechta "qiyin" vakansiyalar (L1 score 0.40-0.55 orasida) beriladi.
Har birini chuqur tahlil qilib yangilangan score ber.
Javob JSON array:
[{"external_id": "...", "score": 0.72, "reason": "..."}]"""


async def rerank_vacancies(user_profile: dict, candidates: list[dict]) -> list[dict]:
    """
    Gemini Flash orqali L2 re-ranking.
    Cost control: oylik $5 limitdan oshsa skip.
    """
    if not candidates:
        return []
    client = get_client()
    prompt = (
        f"Profil:\n{json.dumps(user_profile, ensure_ascii=False)}\n\n"
        f"Vakansiyalar:\n{json.dumps(candidates, ensure_ascii=False)}"
    )
    try:
        interaction = client.interactions.create(
            model="gemini-3.8-flash",
            system_instruction=SYSTEM_INSTRUCTION,
            input=prompt,
            store=False,
        )
        results = json.loads(interaction.output_text or "[]")
        log.info("rerank_done", count=len(results))
        return results
    except Exception as e:
        log.error("reranker_error", error=str(e))
        return candidates
