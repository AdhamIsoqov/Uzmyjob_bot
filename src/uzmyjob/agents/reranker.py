"""L2 Gemini Flash Re-ranker — faqat 0.35–0.65 (yoki 0.40–0.55) threshold orasidagi vakansiyalar uchun."""
import asyncio
import json
import time
from datetime import datetime

from google.genai import types

from uzmyjob.agents.client import get_client
from uzmyjob.utils.logger import log
from uzmyjob.utils.metrics import LLM_COST_DOLLARS_TOTAL, LLM_RERANK_CALLS_TOTAL

SYSTEM_INSTRUCTION = """Sen vakansiya re-ranklash (chuqur tahlil) agentisan.
Foydalanuvchi profili va L1 filtrlashda noaniq (chegara zonasida) bo'lgan vakansiya beriladi.
Texnologik stek, tajriba, shahar, format va talablarni chuqur tahlil qilib, 0.0–1.0 oralig'ida aniq score va qisqa asos (reason) ber.
Javob faqat JSON formatida bo'lsin:
{"match_score": 0.78, "reason": "Nomzodning FastAPI va Docker tajribasi loyiha talablariga to'liq mos keladi"}"""

BATCH_SYSTEM_INSTRUCTION = """Sen vakansiya re-ranklash agentisan.
Foydalanuvchi profili va bir nechta vakansiyalar beriladi.
Har bir vakansiyani chuqur tahlil qilib yangilangan score ber.
Javob faqat JSON array bo'lsin:
[{"external_id": "...", "match_score": 0.72, "reason": "..."}]"""


class CostBudgetTracker:
    """Oylik $5 xarajat chegarasini (Cost-gating) nazorat qiluvchi hisoblagich."""

    def __init__(self, monthly_budget_dollars: float = 5.0, cost_per_call: float = 0.0002):
        self.monthly_budget = monthly_budget_dollars
        self.cost_per_call = cost_per_call
        self.current_month = datetime.now().strftime("%Y-%m")
        self.total_spent = 0.0

    def _check_and_reset_month(self) -> None:
        now_month = datetime.now().strftime("%Y-%m")
        if now_month != self.current_month:
            self.current_month = now_month
            self.total_spent = 0.0

    def can_spend(self, cost: float | None = None) -> bool:
        self._check_and_reset_month()
        c = cost or self.cost_per_call
        return (self.total_spent + c) <= self.monthly_budget

    def record_spend(self, cost: float | None = None) -> float:
        self._check_and_reset_month()
        c = cost or self.cost_per_call
        self.total_spent += c
        LLM_COST_DOLLARS_TOTAL.inc(c)
        return self.total_spent


budget_tracker = CostBudgetTracker()


async def rerank_single_vacancy(
    user_profile: dict,
    vacancy: dict,
    l1_score: float,
    l1_reason: str,
) -> tuple[float, str]:
    """
    Yagona chegaradagi vakansiyani Gemini Flash orqali qayta baholash.
    """
    if not budget_tracker.can_spend():
        log.warning("llm_rerank_skipped_budget_limit", total_spent=budget_tracker.total_spent)
        LLM_RERANK_CALLS_TOTAL.labels(status="cost_limited").inc()
        return l1_score, f"{l1_reason} (L2 limit)"

    try:
        client = get_client()
        prompt = (
            f"Foydalanuvchi profili:\n{json.dumps(user_profile, ensure_ascii=False)}\n\n"
            f"Vakansiya:\n{json.dumps(vacancy, ensure_ascii=False)}\n\n"
            f"Dastlabki L1 ball: {l1_score}"
        )
        t0 = time.time()
        interaction = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                ),
            ),
            timeout=10.0,
        )
        duration = time.time() - t0
        raw_text = (interaction.text or "").strip()

        # Agar JSON blok bilan o'ralgan bo'lsa (```json ... ```)
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            raw_text = raw_text.removeprefix("json")
        raw_text = raw_text.strip()

        data = json.loads(raw_text)
        score = float(data.get("match_score", l1_score))
        reason = data.get("reason", l1_reason)

        budget_tracker.record_spend()
        LLM_RERANK_CALLS_TOTAL.labels(status="success").inc()
        log.info("rerank_single_success", vacancy_id=vacancy.get("external_id"), score=score, duration=round(duration, 3))
        return score, reason
    except Exception as e:
        log.error("rerank_single_error", error=str(e), vacancy_id=vacancy.get("external_id"))
        LLM_RERANK_CALLS_TOTAL.labels(status="error").inc()
        return l1_score, l1_reason


async def rerank_vacancies(user_profile: dict, candidates: list[dict]) -> list[dict]:
    """
    Bir nechta chegaradagi vakansiyalarni partiyalab (batch) L2 re-ranking qilish.
    """
    if not candidates:
        return []

    if not budget_tracker.can_spend():
        log.warning("batch_rerank_skipped_budget_limit")
        LLM_RERANK_CALLS_TOTAL.labels(status="cost_limited").inc()
        return candidates

    try:
        client = get_client()
        prompt = (
            f"Profil:\n{json.dumps(user_profile, ensure_ascii=False)}\n\n"
            f"Vakansiyalar:\n{json.dumps(candidates, ensure_ascii=False)}"
        )
        interaction = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=BATCH_SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                ),
            ),
            timeout=15.0,
        )
        raw_text = (interaction.text or "").strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            raw_text = raw_text.removeprefix("json")
        raw_text = raw_text.strip()

        results = json.loads(raw_text)
        budget_tracker.record_spend()
        LLM_RERANK_CALLS_TOTAL.labels(status="success").inc()
        log.info("batch_rerank_done", count=len(results))
        return results
    except Exception as e:
        log.error("reranker_batch_error", error=str(e))
        LLM_RERANK_CALLS_TOTAL.labels(status="error").inc()
        return candidates
