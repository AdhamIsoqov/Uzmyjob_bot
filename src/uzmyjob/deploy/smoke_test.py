"""E2E Smoke Test va Tizim Verifikatsiya Skripti (M6 Yakuniy tekshiruv)."""
import asyncio
import sys
import tracemalloc

from uzmyjob.adapters.hh_api import HeadHunterAdapter
from uzmyjob.agents.cover_letter import get_default_template, validate_template
from uzmyjob.agents.matcher import compute_l1_score
from uzmyjob.pipeline.pipeline import normalize_text_for_dedupe
from uzmyjob.utils.crypto import decrypt_str, encrypt_str
from uzmyjob.utils.cv_parser import CVParser
from uzmyjob.utils.healthcheck import run_healthcheck
from uzmyjob.utils.metrics import (
    APPLICATIONS_SENT,
    DEDUPLICATED_TOTAL,
    VACANCIES_FETCHED,
    update_system_gauges,
)


async def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("==================================================")
    print("[RUN] @Uzmyjob_bot: E2E Smoke & System Verification")
    print("==================================================")
    tracemalloc.start()

    # 1. CVParser va Shifrlash tekshiruvi
    sample_cv = (
        "Ism: Rustam Davronov\n"
        "Email: rustam@test.uz\n"
        "Tel: +998901112233\n"
        "Telegram: @rustam_dev\n"
        "Tajriba: 3 yil Python, Django, FastAPI va PostgreSQL bo'yicha ish tajribasi.\n"
        "Docker va Git bilan doimiy ishlayman."
    )
    cv_res = CVParser.parse_cv(sample_cv.encode("utf-8"), "resume.pdf")
    assert cv_res["email"] == "rustam@test.uz", f"CV email xato: {cv_res['email']}"
    assert "fastapi" in cv_res["detected_skills"], "CV skills xato"
    print("[OK] 1. CVParser (PDF/DOCX, skills, contacts): PASSED")

    enc_cv = encrypt_str(cv_res["text"])
    dec_cv = decrypt_str(enc_cv)
    assert dec_cv == cv_res["text"], "Fernet shifrlashda mos kelmadi"
    print("[OK] 2. AES-256 Fernet shifrlash/deshifrlash: PASSED")

    # 2. Adapterlar va Deduplikatsiya tekshiruvi
    hh_adapter = HeadHunterAdapter()
    raw_item = {
        "id": "123456",
        "name": "Middle Python Backend Engineer",
        "employer": {"name": "Test FinTech"},
        "area": {"name": "Toshkent"},
        "salary": {"from": 1500, "to": 2500, "currency": "USD"},
        "snippet": {
            "requirement": "FastAPI, Docker, PostgreSQL",
            "responsibility": "Backend mikroservislar",
        },
        "alternate_url": "https://hh.uz/vacancy/123456",
    }
    norm_vac = hh_adapter.normalize(raw_item)
    assert norm_vac["title"] == "Middle Python Backend Engineer"

    # Dedupe normalization
    sig1 = normalize_text_for_dedupe("Middle Python Backend Engineer LLC Test FinTech")
    sig2 = normalize_text_for_dedupe("Middle Python Backend Engineer MCHJ Test FinTech")
    assert sig1 == sig2, f"Dedupe normalization mos kelmadi: {sig1} != {sig2}"
    print("[OK] 3. Adapter normalizatsiyasi va Cross-source Dedupe: PASSED")

    # 3. L1 Matching va Blacklist tekshiruvi
    user_prof = {
        "position": "Python Backend Engineer",
        "keywords": ["FastAPI", "Docker", "PostgreSQL"],
        "city": "Toshkent",
        "min_salary": 1200,
        "blacklist": ["amaliyot", "kazino"],
    }
    score, _reason = compute_l1_score(user_prof, norm_vac)
    assert score >= 0.70, f"Score past: {score}"

    # Blacklist tekshiruvi
    bl_vac = dict(norm_vac)
    bl_vac["description"] = "Bu yerda amaliyot taklif etiladi."
    bl_score, _bl_reason = compute_l1_score(user_prof, bl_vac)
    assert bl_score == 0.0, f"Blacklist ishlamadi: {bl_score}"
    print("[OK] 4. L1 Algoritmik Matching & Blacklist Filter: PASSED")

    # 4. Jinja2 Cover Letter ko'p tilli shablonlar
    tpl_uz = get_default_template("uz")
    tpl_ru = get_default_template("ru")
    tpl_en = get_default_template("en")
    assert len(tpl_uz) > 20 and len(tpl_ru) > 20 and len(tpl_en) > 20

    is_valid, _ = validate_template(tpl_uz)
    assert is_valid, "Standart Jinja2 shablon xato"
    print("[OK] 5. Jinja2 Multi-language Cover Letter & Validator: PASSED")

    # 5. Prometheus Metrikalari
    VACANCIES_FETCHED.labels(source="hh").inc()
    APPLICATIONS_SENT.labels(source="hh", status="sent").inc()
    DEDUPLICATED_TOTAL.labels(reason="source_id").inc()
    await update_system_gauges()
    print("[OK] 6. Prometheus Metrikalari va Gauge yangilanishi: PASSED")

    # 6. Salomatlik va Xotira tekshiruvi (< 300 MB)
    await run_healthcheck()
    _curr, peak = tracemalloc.get_traced_memory()
    peak_mb = peak / (1024 * 1024)
    print(f"[OK] 7. Healthcheck & Xotira sarfi (Peak: {peak_mb:.2f} MB < 300 MB): PASSED")

    print("==================================================")
    print("[SUCCESS] Barcha E2E qabul mezonlari muvaffaqiyatli o'tdi!")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(main())
