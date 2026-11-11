"""Bot handlerlari, middleware, XSS escape, duplicate apply va Alembic migratsiya testlari."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import alembic.command
import alembic.config
import pytest
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import uzmyjob.models  # noqa: F401
from uzmyjob.bot.handlers.start import cmd_start
from uzmyjob.bot.handlers.stop import callback_confirm_delete_account, cmd_delete_account
from uzmyjob.bot.handlers.vacancies import _record_application
from uzmyjob.bot.middleware import ThrottlingMiddleware
from uzmyjob.models.application import Application
from uzmyjob.models.base import Base
from uzmyjob.models.user import User
from uzmyjob.models.vacancy import Vacancy


@pytest.mark.asyncio
async def test_throttling_middleware_limits_messages_and_callbacks():
    """ThrottlingMiddleware Message va CallbackQuery so'rovlarini cheklashi kerak."""
    mw = ThrottlingMiddleware(rate=2, window=60.0)
    handler = AsyncMock(return_value="ok")

    msg = MagicMock(spec=Message)
    msg.from_user = SimpleNamespace(id=1001)
    msg.answer = AsyncMock()

    cb = MagicMock(spec=CallbackQuery)
    cb.from_user = SimpleNamespace(id=1001)
    cb.answer = AsyncMock()

    assert await mw(handler, msg, {}) == "ok"
    assert await mw(handler, cb, {}) == "ok"
    # 3-so'rov limitdan oshadi va bloklanadi
    assert await mw(handler, cb, {}) is None
    cb.answer.assert_awaited_once()
    assert handler.await_count == 2


@pytest.mark.asyncio
async def test_start_reactivates_user_and_escapes_html(tmp_path):
    """/start nofaol foydalanuvchini qayta faollashtirishi va HTML ni escape qilishi kerak."""
    db_file = tmp_path / "start_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add(
            User(
                telegram_id=777001,
                position="<script>alert(1)</script> Python",
                city="<b>Toshkent</b>",
                is_active=False,
            )
        )
        await session.commit()

    message = AsyncMock()
    message.from_user = SimpleNamespace(id=777001, first_name="<b>Adham</b>")
    state = AsyncMock()

    with patch("uzmyjob.bot.handlers.start.AsyncSessionLocal", session_factory):
        await cmd_start(message, state)

    async with session_factory() as session:
        user = (await session.execute(select(User).where(User.telegram_id == 777001))).scalar_one()
        assert user.is_active is True

    all_texts = " ".join(str(call.args[0]) for call in message.answer.await_args_list if call.args)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in all_texts
    assert "&lt;b&gt;Adham&lt;/b&gt;" in all_texts
    assert "<script>" not in all_texts

    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_account_two_step_confirmation(tmp_path):
    """/delete_account avval tasdiqlash tugmasini yuborishi, tasdiqdan keyingina o'chirishi kerak."""
    db_file = tmp_path / "delete_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = User(telegram_id=888002, position="DevOps")
        session.add(user)
        await session.flush()
        session.add(
            Application(user_id=user.id, source="hh", external_id="vac-1")
        )
        await session.commit()

    msg = AsyncMock()
    msg.from_user = SimpleNamespace(id=888002)

    with patch("uzmyjob.bot.handlers.stop.AsyncSessionLocal", session_factory):
        await cmd_delete_account(msg)

        # Birinchi bosqichda foydalanuvchi o'chirilmagan bo'lishi kerak
        async with session_factory() as session:
            assert (
                await session.execute(select(User).where(User.telegram_id == 888002))
            ).scalar_one_or_none() is not None

        cb = AsyncMock()
        cb.from_user = SimpleNamespace(id=888002)
        cb.message = AsyncMock()
        await callback_confirm_delete_account(cb)

        async with session_factory() as session:
            assert (
                await session.execute(select(User).where(User.telegram_id == 888002))
            ).scalar_one_or_none() is None
            assert (
                await session.execute(select(Application))
            ).scalars().all() == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_record_application_handles_duplicate_gracefully(tmp_path):
    """Takroriy murojaat IntegrityError bilan yiqilmay False qaytarishi kerak."""
    db_file = tmp_path / "apply_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = User(telegram_id=999003, position="Backend")
        vac = Vacancy(
            source="hh",
            external_id="ext-42",
            title="Python Dev",
            url="https://hh.uz/vacancy/ext-42",
        )
        session.add_all([user, vac])
        await session.commit()
        uid, vid = user.id, vac.id

    with patch("uzmyjob.bot.handlers.vacancies.AsyncSessionLocal", session_factory):
        first = await _record_application(uid, "hh", "ext-42", vid)
        second = await _record_application(uid, "hh", "ext-42", vid)

    assert first is True
    assert second is False

    await engine.dispose()


def test_alembic_upgrade_head_on_fresh_sqlite(tmp_path, monkeypatch):
    """Alembic migratsiyalari bo'sh bazada xatosiz head gacha ko'tarilishi kerak."""
    db_file = tmp_path / "alembic_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("POSTGRES_URL", db_url)

    from uzmyjob.config import settings

    old_url = settings.postgres_url
    settings.postgres_url = db_url
    try:
        alembic_cfg = alembic.config.Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        alembic.command.upgrade(alembic_cfg, "head")
    finally:
        settings.postgres_url = old_url

    with sqlite3.connect(db_file) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {"users", "vacancies", "applications", "sources", "alembic_version"}.issubset(
            tables
        )
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        assert version is not None and version[0] == "002_sync_defaults"
