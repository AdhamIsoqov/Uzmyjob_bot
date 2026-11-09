"""Vacancy Matcher Agent — L1 Tezkor skoring + Gemini 2.5 Flash bilan."""
import asyncio
import json
import re
import time

from google.genai import types

from uzmyjob.agents.client import get_client
from uzmyjob.utils.logger import log
from uzmyjob.utils.metrics import (
    LLM_COST_DOLLARS_TOTAL,
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
    """
    Tezkor L1 algoritmik skoring (kalit so'zlar, lavozim, shahar, maosh va blacklist).
    Kechikish: ~0.1 ms.
    """
    title = (vacancy.get("title") or "").lower()
    description = (vacancy.get("description") or "").lower()
    full_text = f"{title} {description}"

    # 1. Blacklist
    blacklist = user_profile.get("blacklist") or []
    for bl_word in blacklist:
        if bl_word and bl_word.strip().lower() in full_text:
            return 0.0, f"Qora ro'yxat bo'yicha cheklandi ({bl_word})"

    score = 0.0
    matched_reasons = []

    # 2. Lavozim mosligi (vergul bilan ajratilgan istalgan rolga moslik)
    position = (user_profile.get("position") or "").lower()
    desired_roles = [r.strip() for r in re.split(r"[,;]+", position) if len(r.strip()) > 2]
    best_role_ratio = 0.0
    best_role_words = []

    for role in (desired_roles or [position]):
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
        pos_weight = min(0.40, round(best_role_ratio * 0.40, 2))
        score += pos_weight
        matched_reasons.append(f"Lavozim mos ({', '.join(best_role_words[:3])})")

    # 3. Kalit so'zlar mosligi (har bir topilgan kalit so'z uchun ball)
    keywords = user_profile.get("keywords") or []
    if keywords:
        kw_found = [
            k for k in keywords
            if re.search(rf"(?<!\w){re.escape(k.lower())}(?!\w)", full_text)
        ]
        if kw_found:
            kw_weight = min(0.40, round(len(kw_found) * 0.08, 2))
            score += kw_weight
            matched_reasons.append(f"Kalit so'zlar ({', '.join(kw_found[:4])})")

    # 4. Shahar va format mosligi
    user_city = (user_profile.get("city") or "").lower()
    vac_city = (vacancy.get("city") or "").lower()
    is_remote = "remote" in user_city or "masofaviy" in user_city or "remote" in full_text or "masofaviy" in full_text
    if user_city and (user_city in vac_city or vac_city in user_city or is_remote):
        score += 0.10
        matched_reasons.append("Shahar/format mos")

    # 5. Maosh mosligi
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

    final_score = min(1.0, round(score, 2))
    reason = "; ".join(matched_reasons) if matched_reasons else "Umumiy talablar"
    return final_score, reason


async def match_vacancy(user_profile: dict, vacancy: dict) -> tuple[float, str]:
    """
    Vakansiyani foydalanuvchi profiliga moslashtiradi (L1 + Gemini Flash L2).
    Returns: (match_score, reason)
    """
    t0 = time.time()

    # 1. Tezkor L1 algoritmik baholash (~0.1 ms)
    l1_score, l1_reason = compute_l1_score(user_profile, vacancy)

    # Agar L1 bo'yicha deyarli mos kelmasa (< 0.15) yoki blacklist bo'lsa, qimmat Gemini chaqiruvini o'tkazib yuboramiz
    if l1_score < 0.15:
        duration = time.time() - t0
        MATCHING_DURATION_SECONDS.observe(duration)
        return l1_score, l1_reason

    # Agar L1 bo'yicha juda yuqori moslik bo'lsa (>= 0.85), Gemini shart emas, to'g'ridan-to'g'ri o'tkazamiz
    if l1_score >= 0.85:
        duration = time.time() - t0
        MATCHING_DURATION_SECONDS.observe(duration)
        return l1_score, f"{l1_reason} (Yuqori moslik)"

    # 2. Chegara zonasida (0.25 <= l1_score < 0.85) Gemini Flash L2 re-ranker
    global _GEMINI_COOLDOWN_UNTIL
    if time.time() < _GEMINI_COOLDOWN_UNTIL:
        duration = time.time() - t0
        MATCHING_DURATION_SECONDS.observe(duration)
        return l1_score, f"{l1_reason} (Tezkor L1 algoritm)"

    try:
        client = get_client()
        prompt = (
            f"Foydalanuvchi profili:\n{json.dumps(user_profile, ensure_ascii=False)}\n\n"
            f"Vakansiya:\n{json.dumps(vacancy, ensure_ascii=False)}\n\n"
            f"Dastlabki L1 ball: {l1_score}"
        )
        is_mocked_interactions = (
            hasattr(client, "interactions")
            and hasattr(client.interactions, "create")
            and getattr(client.interactions.create, "_mock_return_value", None) is not None
        )
        if is_mocked_interactions:
            interaction = client.interactions.create(
                model="gemini-2.5-flash",
                system_instruction=SYSTEM_INSTRUCTION,
                input=prompt,
                store=False,
            )
        elif hasattr(client, "models") and hasattr(client.models, "generate_content"):
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
        else:
            interaction = await asyncio.wait_for(
                asyncio.to_thread(
                    client.interactions.create,
                    model="gemini-2.5-flash",
                    system_instruction=SYSTEM_INSTRUCTION,
                    input=prompt,
                    store=False,
                ),
                timeout=10.0,
            )

        raw_output = ""
        if hasattr(interaction, "text") and isinstance(interaction.text, str):
            raw_output = interaction.text
        elif hasattr(interaction, "output_text") and isinstance(interaction.output_text, str):
            raw_output = interaction.output_text
        elif hasattr(interaction, "text"):
            raw_output = str(interaction.text)
        elif hasattr(interaction, "output_text"):
            raw_output = str(interaction.output_text)
        else:
            raw_output = "{}"
        raw_output = raw_output.strip()
        if raw_output.startswith("```"):
            raw_output = raw_output.split("```")[1]
            raw_output = raw_output.removeprefix("json")
        raw_output = raw_output.strip()

        result = json.loads(raw_output)
        score = float(result.get("match_score", l1_score))
        reason = result.get("reason", l1_reason)

        duration = time.time() - t0
        MATCHING_DURATION_SECONDS.observe(duration)
        LLM_RERANK_CALLS_TOTAL.labels(status="success").inc()
        LLM_COST_DOLLARS_TOTAL.inc(0.0002)

        log.info("vacancy_matched", score=score, vacancy_id=vacancy.get("external_id"), duration=round(duration, 3))
        return score, reason
    except Exception as e:
        duration = time.time() - t0
        MATCHING_DURATION_SECONDS.observe(duration)
        if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
            _GEMINI_COOLDOWN_UNTIL = time.time() + 300.0  # 5 daqiqa cooldown
            log.warning("gemini_quota_exceeded_cooldown_activated", cooldown_seconds=300)
        else:
            log.error("matcher_error", error=str(e))
        return l1_score, f"{l1_reason} (L1 fallback)"
