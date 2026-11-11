"""Vacancy Matcher Agent — L1 Tezkor skoring + Gemini 2.5 Flash L2 re-ranking."""
import json
import re
import time

from uzmyjob.agents.client import generate_gemini_text, get_client, strip_markdown_fences
from uzmyjob.agents.reranker import budget_tracker
from uzmyjob.utils.logger import log
from uzmyjob.utils.metrics import (
    LLM_RERANK_CALLS_TOTAL,
    MATCHING_DURATION_SECONDS,
)

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

_GEMINI_COOLDOWN_UNTIL = 0.0


def compute_l1_score(user_profile: dict, vacancy: dict) -> tuple[float, str]:
    """Tezkor L1 algoritmik skoring (kalit so'zlar, lavozim, shahar, maosh va blacklist)."""
    title = (vacancy.get("title") or "").lower()
    description = (vacancy.get("description") or "").lower()
    full_text = f"{title} {description}"

    blacklist = user_profile.get("blacklist") or []
    for bl_word in blacklist:
        if bl_word and bl_word.strip().lower() in full_text:
            return 0.0, f"Qora ro'yxat bo'yicha cheklandi ({bl_word})"

    score = 0.0
    matched_reasons: list[str] = []

    position = (user_profile.get("position") or "").lower()
    desired_roles = [r.strip() for r in re.split(r"[,;]+", position) if len(r.strip()) > 2]
    best_role_ratio = 0.0
    best_role_words: list[str] = []

    for role in desired_roles or [position]:
        words = [w for w in re.split(r"[\s/]+", role) if len(w) > 2]
        if not words:
            continue
        matched_in_title = [w for w in words if w in title]
        matched_in_desc = [w for w in words if w in full_text]
        ratio = min(1.0, (len(matched_in_title) * 1.0 + len(matched_in_desc) * 0.4) / len(words))
        if ratio > best_role_ratio:
            best_role_ratio = ratio
            best_role_words = matched_in_title or matched_in_desc

    if best_role_ratio > 0:
        score += min(0.40, round(best_role_ratio * 0.40, 2))
        matched_reasons.append(f"Lavozim mos ({', '.join(best_role_words[:3])})")

    keywords = user_profile.get("keywords") or []
    if keywords:
        kw_found = [
            k for k in keywords
            if k and re.search(rf"(?<!\w){re.escape(k.lower())}(?!\w)", full_text)
        ]
        if kw_found:
            score += min(0.40, round(len(kw_found) * 0.08, 2))
            matched_reasons.append(f"Kalit so'zlar ({', '.join(kw_found[:4])})")

    user_city = (user_profile.get("city") or "").lower()
    vac_city = (vacancy.get("city") or "").lower()
    is_remote = (
        "remote" in user_city
        or "masofaviy" in user_city
        or "remote" in full_text
        or "masofaviy" in full_text
    )
    if user_city and (user_city in vac_city or vac_city in user_city or is_remote):
        score += 0.10
        matched_reasons.append("Shahar/format mos")

    min_sal = user_profile.get("min_salary") or 0
    vac_sal_max = vacancy.get("salary_max")
    if min_sal > 0 and vac_sal_max:
        if vac_sal_max >= min_sal:
            score += 0.10
            matched_reasons.append("Maosh talabga mos")
        else:
            score = max(0.0, score - 0.15)
    elif min_sal > 0 and not vac_sal_max:
        score += 0.05

    final_score = max(0.0, min(1.0, round(score, 2)))
    reason = "; ".join(matched_reasons) if matched_reasons else "Umumiy talablar"
    return final_score, reason


async def match_vacancy(user_profile: dict, vacancy: dict) -> tuple[float, str]:
    """Vakansiyani foydalanuvchi profiliga moslashtiradi (L1 + chegarada Gemini Flash L2)."""
    global _GEMINI_COOLDOWN_UNTIL
    t0 = time.monotonic()

    l1_score, l1_reason = compute_l1_score(user_profile, vacancy)

    if l1_score < 0.25:
        MATCHING_DURATION_SECONDS.observe(time.monotonic() - t0)
        return l1_score, l1_reason

    if l1_score >= 0.85:
        MATCHING_DURATION_SECONDS.observe(time.monotonic() - t0)
        return l1_score, f"{l1_reason} (Yuqori moslik)"

    if time.monotonic() < _GEMINI_COOLDOWN_UNTIL:
        MATCHING_DURATION_SECONDS.observe(time.monotonic() - t0)
        return l1_score, f"{l1_reason} (Tezkor L1 algoritm)"

    if not budget_tracker.can_spend():
        log.warning("matcher_skipped_budget_limit", total_spent=budget_tracker.total_spent)
        LLM_RERANK_CALLS_TOTAL.labels(status="cost_limited").inc()
        MATCHING_DURATION_SECONDS.observe(time.monotonic() - t0)
        return l1_score, f"{l1_reason} (Budjet limiti)"

    try:
        prompt = (
            f"Foydalanuvchi profili:\n{json.dumps(user_profile, ensure_ascii=False)}\n\n"
            f"Vakansiya:\n{json.dumps(vacancy, ensure_ascii=False)}\n\n"
            f"Dastlabki L1 ball: {l1_score}"
        )
        raw_output = await generate_gemini_text(
            prompt=prompt,
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            timeout=10.0,
            client=get_client(),
        )
        result = json.loads(strip_markdown_fences(raw_output) or "{}")
        raw_score = float(result.get("match_score", l1_score))
        score = max(0.0, min(1.0, raw_score))
        reason = str(result.get("reason") or l1_reason)[:300]

        duration = time.monotonic() - t0
        MATCHING_DURATION_SECONDS.observe(duration)
        LLM_RERANK_CALLS_TOTAL.labels(status="success").inc()
        budget_tracker.record_spend()

        log.info(
            "vacancy_matched",
            score=score,
            vacancy_id=vacancy.get("external_id"),
            duration=round(duration, 3),
        )
        return score, reason
    except Exception as exc:
        MATCHING_DURATION_SECONDS.observe(time.monotonic() - t0)
        LLM_RERANK_CALLS_TOTAL.labels(status="error").inc()
        if "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc):
            _GEMINI_COOLDOWN_UNTIL = time.monotonic() + 300.0
            log.warning("gemini_quota_exceeded_cooldown_activated", cooldown_seconds=300)
        else:
            log.error("matcher_error", error=str(exc))
        return l1_score, f"{l1_reason} (L1 fallback)"
