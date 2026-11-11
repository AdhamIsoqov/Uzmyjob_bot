"""Xavfsizlik, modellar, parser, healthcheck va backup testlari."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import uzmyjob.models  # noqa: F401
from uzmyjob.agents.cover_letter import MAX_TEMPLATE_LENGTH, validate_template
from uzmyjob.agents.matcher import match_vacancy
from uzmyjob.agents.reranker import CostBudgetTracker
from uzmyjob.bot.handlers.stats import _sanitize_csv_cell
from uzmyjob.models.base import Base
from uzmyjob.models.source import Source
from uzmyjob.models.user import User
from uzmyjob.pipeline.dead_letter import SourceHealthTracker
from uzmyjob.utils.backup import _build_pg_dump_args_and_env, create_database_backup
from uzmyjob.utils.cv_parser import CVParser
from uzmyjob.utils.healthcheck import run_healthcheck


@pytest.mark.parametrize(
    "malicious_tpl",
    [
        "{{ ''.__class__.__mro__ }}",
        "{{ config.items() }}",
        "{{ unknown_variable }}",
        "{% for x in range(10) %}{{ x }}{% endfor %}",
        "A" * (MAX_TEMPLATE_LENGTH + 1),
    ],
)
def test_cover_letter_rejects_ssti_and_disallowed_templates(malicious_tpl: str):
    """SSTI yuklari, noma'lum o'zgaruvchilar va haddan ziyod uzun shablonlar rad etilishi kerak."""
    is_valid, _msg = validate_template(malicious_tpl)
    assert is_valid is False


def test_cover_letter_accepts_safe_template():
    """Ruxsat etilgan o'zgaruvchilar bilan to'g'ri shablon qabul qilinadi."""
    ok, _msg = validate_template(
        "Salom! {{ company_name }} dagi {{ vacancy_title }} uchun {{ years_exp }} yillik tajribam bor."
    )
    assert ok is True


@pytest.mark.asyncio
async def test_matcher_clamps_out_of_range_scores():
    """Gemini qaytargan ball [0.0, 1.0] oralig'iga siqilishi kerak."""
    profile = {"position": "Backend Developer", "keywords": ["Python", "Django"]}
    vacancy = {"title": "Python Django Backend Developer", "external_id": "clamp-1"}

    mock_resp = MagicMock()
    mock_resp.text = '{"match_score": 2.75, "reason": "Juda mos"}'

    with patch("uzmyjob.agents.matcher.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_resp
        mock_get_client.return_value = mock_client

        score, _reason = await match_vacancy(profile, vacancy)
        assert score == 1.0

    mock_resp.text = '{"match_score": -0.5, "reason": "Mos emas"}'
    with patch("uzmyjob.agents.matcher.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_resp
        mock_get_client.return_value = mock_client

        score, _reason = await match_vacancy(profile, vacancy)
        assert score == 0.0


def test_budget_tracker_limits_and_spend():
    """CostBudgetTracker budjet limitidan oshishiga yo'l qo'ymasligi kerak."""
    tracker = CostBudgetTracker(monthly_budget_dollars=0.0003, cost_per_call=0.0002)
    assert tracker.can_spend() is True
    tracker.record_spend()
    assert tracker.can_spend() is False


def test_cv_parser_rejects_doc_and_corrupt_containers():
    """.doc rad etilishi, skaner/buzilgan PDF va DOCX esa ValueError berishi kerak."""
    with pytest.raises(ValueError, match="DOCX"):
        CVParser.parse_cv(b"legacy-doc", "old_resume.doc")

    with pytest.raises(ValueError):
        CVParser.parse_cv(b"%PDF-1.4\x00\xff\xfe", "scan.pdf")

    with pytest.raises(ValueError):
        CVParser.parse_cv(b"not-a-valid-zip-docx", "broken.docx")

    parsed_txt = CVParser.parse_cv(
        b"Backend Python FastAPI Docker dev@example.com +998901112233",
        "resume.txt",
    )
    assert parsed_txt["email"] == "dev@example.com"
    assert "python" in parsed_txt["detected_skills"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("=CMD|' /C calc'!A0", "'=CMD|' /C calc'!A0"),
        ("+SUM(1,2)", "'+SUM(1,2)"),
        ("-100", "'-100"),
        ("@evil", "'@evil"),
        ("Normal Company", "Normal Company"),
        (None, ""),
    ],
)
def test_csv_formula_injection_sanitized(raw, expected: str):
    """CSV/DDE formula belgilari apostrof bilan zararsizlantirilishi kerak."""
    assert _sanitize_csv_cell(raw) == expected


@pytest.mark.asyncio
async def test_biginteger_user_and_source_health_null_error_count(tmp_path):
    """BigInteger telegram_id va error_count=None bo'lgan Source xatosiz ishlashi kerak."""
    db_file = tmp_path / "models_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    large_tg_id = 6_500_000_000
    async with session_factory() as session:
        user = User(telegram_id=large_tg_id, position="Python Dev")
        session.add(user)
        src = Source(name="hh_test", error_count=None)
        session.add(src)
        await session.commit()

    with patch("uzmyjob.pipeline.dead_letter.AsyncSessionLocal", session_factory):
        for _ in range(SourceHealthTracker.MAX_CONSECUTIVE_ERRORS):
            await SourceHealthTracker.record_failure("hh_test", "Timeout")

        async with session_factory() as session:
            from sqlalchemy import select

            updated = (await session.execute(select(Source).where(Source.name == "hh_test"))).scalar_one()
            assert updated.error_count == SourceHealthTracker.MAX_CONSECUTIVE_ERRORS
            assert updated.status == "error"

        await SourceHealthTracker.record_success("hh_test")
        async with session_factory() as session:
            from sqlalchemy import select

            recovered = (await session.execute(select(Source).where(Source.name == "hh_test"))).scalar_one()
            assert recovered.error_count == 0
            assert recovered.status == "ok"

    await engine.dispose()


@pytest.mark.asyncio
async def test_healthcheck_hides_internal_db_error_details():
    """DB xatosi yuz berganda ichki parol/stacktrace JSON javobda chiqmasligi kerak."""
    broken_cm = MagicMock()
    broken_cm.__aenter__ = AsyncMock(
        side_effect=RuntimeError("FATAL: password authentication failed for postgresql://user:secret@host/db")
    )
    broken_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("uzmyjob.utils.healthcheck.AsyncSessionLocal", return_value=broken_cm):
        report = await run_healthcheck()

    assert report["status"] == "unhealthy"
    assert report["database"] == "disconnected"
    assert report["errors"] == ["Database connection failed"]
    assert "secret" not in str(report)


def test_build_pg_dump_args_avoids_password_cli_exposure(tmp_path):
    """pg_dump buyrug'i parolni CLI argumentiga emas PGPASSWORD env ga qo'yishi kerak."""
    raw = Path(tmp_path) / "dump.sql"
    args, env = _build_pg_dump_args_and_env(
        "postgresql+asyncpg://uzmyjob:s3cr3t%21pass@db.internal:5432/prod_db",
        raw,
    )
    assert "s3cr3t!pass" not in " ".join(args)
    assert env["PGPASSWORD"] == "s3cr3t!pass"
    assert "--host" in args and "db.internal" in args


@pytest.mark.asyncio
async def test_create_database_backup_skips_sqlite(tmp_path):
    """SQLite rejimida backup xavfsiz o'tkazib yuborilishi kerak."""
    with patch("uzmyjob.utils.backup.settings") as mock_settings:
        mock_settings.postgres_url = f"sqlite+aiosqlite:///{(tmp_path / 'dev.db').as_posix()}"
        res = await create_database_backup(output_dir=str(tmp_path))
        assert res is None
