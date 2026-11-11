"""L2 Gemini Flash Re-ranker va oylik LLM budjet nazorati."""
import json
import time
from datetime import UTC, datetime

from uzmyjob.agents.client import generate_gemini_text, get_client, strip_markdown_fences
from uzmyjob.config import settings
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
    """Oylik xarajat chegarasini (Cost-gating) nazorat qiluvchi hisoblagich."""

    def __init__(self, monthly_budget_dollars: float = 5.0, cost_per_call: float = 0.0002) -> None:
        self.monthly_budget = monthly_budget_dollars
        self.cost_per_call = cost_per_call
        self.current_month = datetime.now(UTC).strftime("%Y-%m")
        self.total_spent = 0.0

    def _check_and_reset_month(self) -> None:
        now_month = datetime.now(UTC).strftime("%Y-%m")
        if now_month != self.current_month:
            self.current_month = now_month
            self.total_spent = 0.0

    def can_spend(self, cost: float | None = None) -> bool:
        self._check_and_reset_month()
        c = cost if cost is not None else self.cost_per_call
        return (self.total_spent + c) <= self.monthly_budget

    def record_spend(self, cost: float | None = None) -> float:
        self._check_and_reset_month()
        c = cost if cost is not None else self.cost_per_call
        self.total_spent += c
        LLM_COST_DOLLARS_TOTAL.inc(c)
        return self.total_spent


budget_tracker = CostBudgetTracker(
    monthly_budget_dollars=settings.gemini_monthly_cost_limit_usd
)


async def rerank_single_vacancy(
    user_profile: dict,
    vacancy: dict,
    l1_score: float,
    l1_reason: str,
) -> tuple[float, str]:
    """Yagona chegaradagi vakansiyani Gemini Flash orqali qayta baholash."""
    if not budget_tracker.can_spend():
        log.warning("llm_rerank_skipped_budget_limit", total_spent=budget_tracker.total_spent)
        LLM_RERANK_CALLS_TOTAL.labels(status="cost_limited").inc()
        return l1_score, f"{l1_reason} (L2 limit)"

    try:
        prompt = (
            f"Foydalanuvchi profili:\n{json.dumps(user_profile, ensure_ascii=False)}\n\n"
            f"Vakansiya:\n{json.dumps(vacancy, ensure_ascii=False)}\n\n"
            f"Dastlabki L1 ball: {l1_score}"
        )
        t0 = time.monotonic()
        raw_text = await generate_gemini_text(
            prompt=prompt,
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            timeout=10.0,
            client=get_client(),
        )
        duration = time.monotonic() - t0
        data = json.loads(strip_markdown_fences(raw_text) or "{}")
        raw_score = float(data.get("match_score", l1_score))
        score = max(0.0, min(1.0, raw_score))
        reason = str(data.get("reason") or l1_reason)[:300]

        budget_tracker.record_spend()
        LLM_RERANK_CALLS_TOTAL.labels(status="success").inc()
        log.info(
            "rerank_single_success",
            vacancy_id=vacancy.get("external_id"),
            score=score,
            duration=round(duration, 3),
        )
        return score, reason
    except Exception as exc:
        log.error("rerank_single_error", error=str(exc), vacancy_id=vacancy.get("external_id"))
        LLM_RERANK_CALLS_TOTAL.labels(status="error").inc()
        return l1_score, l1_reason


async def rerank_vacancies(user_profile: dict, candidates: list[dict]) -> list[dict]:
    """Bir nechta chegaradagi vakansiyalarni partiyalab (batch) L2 re-ranking qilish."""
    if not candidates:
        return []

    if not budget_tracker.can_spend():
        log.warning("batch_rerank_skipped_budget_limit")
        LLM_RERANK_CALLS_TOTAL.labels(status="cost_limited").inc()
        return candidates

    try:
        prompt = (
            f"Profil:\n{json.dumps(user_profile, ensure_ascii=False)}\n\n"
            f"Vakansiyalar:\n{json.dumps(candidates, ensure_ascii=False)}"
        )
        raw_text = await generate_gemini_text(
            prompt=prompt,
            system_instruction=BATCH_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            timeout=15.0,
            client=get_client(),
        )
        results = json.loads(strip_markdown_fences(raw_text) or "[]")
        budget_tracker.record_spend()
        LLM_RERANK_CALLS_TOTAL.labels(status="success").inc()
        log.info("batch_rerank_done", count=len(results))
        return results
    except Exception as exc:
        log.error("reranker_batch_error", error=str(exc))
        LLM_RERANK_CALLS_TOTAL.labels(status="error").inc()
        return candidates
