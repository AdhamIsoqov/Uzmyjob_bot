"""Bot kirish nuqtasi — aiogram 3, Webhook/Polling, Healthcheck va APScheduler."""
import asyncio
from datetime import UTC, datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select

import uzmyjob.models  # noqa: F401
from uzmyjob.agents.reranker import budget_tracker
from uzmyjob.apply.hh_apply import HeadHunterApplyClient
from uzmyjob.bot.handlers import hh_auth, profil, start, stats, stop, vacancies, wizard
from uzmyjob.bot.middleware import ThrottlingMiddleware
from uzmyjob.config import settings
from uzmyjob.models.application import Application
from uzmyjob.models.base import AsyncSessionLocal, Base, engine
from uzmyjob.models.user import User
from uzmyjob.models.vacancy import Vacancy
from uzmyjob.pipeline.pipeline import JobPipeline
from uzmyjob.utils.backup import create_database_backup
from uzmyjob.utils.crypto import decrypt_str, encrypt_str
from uzmyjob.utils.healthcheck import run_healthcheck
from uzmyjob.utils.logger import log, setup_logging
from uzmyjob.utils.metrics import start_prometheus_metrics_server, update_system_gauges


async def scheduled_pipeline_job(pipeline: JobPipeline):
    """Har 15 daqiqada yangi vakansiyalarni tekshirish va xabardor qilish."""
    log.info("scheduled_pipeline_job_started")
    try:
        stats_res = await pipeline.run_once()
        log.info("scheduled_pipeline_job_finished", **stats_res)
    except Exception as e:
        log.error("scheduled_pipeline_job_error", error=str(e))


async def scheduled_token_refresh_job():
    """Har 1 soatda hh.uz OAuth2 tokenlarini tekshirish va muddati tugayotganlarini yangilash."""
    log.info("scheduled_token_refresh_job_started")
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.hh_refresh_token_enc.isnot(None), User.is_active == True)
            users = (await session.execute(stmt)).scalars().all()
            hh_client = HeadHunterApplyClient()

            for u in users:
                needs_refresh = False
                if not u.hh_token_expires_at or u.hh_token_expires_at <= datetime.now(UTC) + timedelta(hours=2):
                    needs_refresh = True

                if needs_refresh and u.hh_refresh_token_enc:
                    rt = decrypt_str(u.hh_refresh_token_enc)
                    res = await hh_client.refresh_access_token(rt)
                    if res and "access_token" in res:
                        u.hh_access_token_enc = encrypt_str(res["access_token"])
                        if "refresh_token" in res:
                            u.hh_refresh_token_enc = encrypt_str(res["refresh_token"])
                        expires_in = res.get("expires_in", 1209600)
                        u.hh_token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
                        await session.commit()
                        log.info("hh_token_refreshed_for_user", user_id=u.id)
    except Exception as e:
        log.error("scheduled_token_refresh_job_error", error=str(e))


async def scheduled_daily_report_job():
    """Har kuni soat 22:00 da kunlik umumiy hisobotni logga yozish."""
    log.info("scheduled_daily_report_job_started")
    try:
        async with AsyncSessionLocal() as session:
            users_count = (await session.execute(select(func.count()).select_from(User).where(User.is_active == True))).scalar() or 0
            vac_count = (await session.execute(select(func.count()).select_from(Vacancy))).scalar() or 0
            app_count = (await session.execute(select(func.count()).select_from(Application))).scalar() or 0

            log.info(
                "daily_report_summary",
                active_users=users_count,
                total_vacancies=vac_count,
                total_applications=app_count,
                llm_spent_dollars=round(budget_tracker.total_spent, 4),
            )
    except Exception as e:
        log.error("scheduled_daily_report_job_error", error=str(e))


async def scheduled_backup_job():
    """Har kuni soat 03:00 da ma'lumotlar bazasini shifrlangan zaxiraga olish."""
    log.info("scheduled_backup_job_started")
    try:
        backup_path = await create_database_backup()
        log.info("scheduled_backup_job_finished", path=backup_path)
    except Exception as e:
        log.error("scheduled_backup_job_error", error=str(e))


async def handle_healthcheck(_request: web.Request) -> web.Response:
    """HTTP /health endpoint — Docker, VPS va Render healthcheck uchun."""
    report = await run_healthcheck()
    status_code = 200 if report.get("status") == "healthy" else 503
    return web.json_response(report, status=status_code)


async def handle_metrics(_request: web.Request) -> web.Response:
    """HTTP /metrics endpoint — Prometheus va Render yagona portli monitoring uchun."""
    await update_system_gauges()
    return web.Response(body=generate_latest(), content_type=CONTENT_TYPE_LATEST)


async def apply_database_migrations():
    """Alembic migratsiyalarini avtomatik bajarish, xato bo'lsa xavfsiz create_all fallback."""
    try:
        import alembic.command
        import alembic.config

        alembic_cfg = alembic.config.Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", settings.postgres_url)
        await asyncio.to_thread(alembic.command.upgrade, alembic_cfg, "head")
        log.info("alembic_migrations_applied_successfully")
    except Exception as e:
        log.warning("alembic_migration_fallback_to_create_all", error=str(e))
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            log.info("database_schema_ready_via_create_all")
        except Exception as err:
            log.warning("database_schema_init_warning", error=str(err))


async def main():
    setup_logging()
    log.info("bot_starting")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Middleware
    dp.message.middleware(ThrottlingMiddleware(rate=settings.throttle_rate))

    # Routerlar
    dp.include_router(start.router)
    dp.include_router(wizard.router)
    dp.include_router(profil.router)
    dp.include_router(stats.router)
    dp.include_router(stop.router)
    dp.include_router(vacancies.router)
    dp.include_router(hh_auth.router)

    # Prometheus server (port 8000, faqat local dev uchun)
    start_prometheus_metrics_server(port=8000)

    # Baza jadvallarini tekshirish / migratsiyalarni bajarish
    await apply_database_migrations()

    # Background Pipeline Scheduler
    pipeline = JobPipeline(bot=bot)
    scheduler = AsyncIOScheduler()

    # 1. Vakansiya tekshiruvi (har 15 daqiqada)
    scheduler.add_job(
        scheduled_pipeline_job,
        "interval",
        minutes=settings.poll_interval_minutes,
        args=[pipeline],
        id="job_pipeline_interval",
    )

    # 2. hh.uz OAuth2 Token refresh (har 1 soatda)
    scheduler.add_job(
        scheduled_token_refresh_job,
        "interval",
        hours=1,
        id="token_refresh_interval",
    )

    # 3. Kunlik hisobot (har 22:00 da)
    scheduler.add_job(
        scheduled_daily_report_job,
        "cron",
        hour=22,
        minute=0,
        id="daily_report_cron",
    )

    # 4. Avtomatik shifrlangan backup (har kuni 03:00 da)
    scheduler.add_job(
        scheduled_backup_job,
        "cron",
        hour=3,
        minute=0,
        id="backup_cron",
    )

    scheduler.start()
    log.info("scheduler_started", interval_minutes=settings.poll_interval_minutes)

    # aiohttp web ilova (Healthcheck, Webhook va Metrics uchun)
    app = web.Application()
    app.router.add_get("/health", handle_healthcheck)
    app.router.add_get("/metrics", handle_metrics)

    runner = web.AppRunner(app)
    await runner.setup()

    # Telegram "Menu" tugmasi uchun buyruqlar ro'yxatini sozlash
    try:
        from aiogram.types import BotCommand
        commands = [
            BotCommand(command="profil", description="👤 Mening profilim va sozlamalar"),
            BotCommand(command="vacancies", description="💼 Mos vakansiyalarni ko'rish"),
            BotCommand(command="statistika", description="📊 Ariza va tahlillar statistikasi"),
            BotCommand(command="wizard", description="🔄 Profilni qayta sozlash (Wizard)"),
            BotCommand(command="hh_auth", description="🔴 hh.uz hisobini ulash (OAuth2)"),
            BotCommand(command="yordam", description="ℹ️ Qo'llanma va yordam"),
            BotCommand(command="start", description="🏠 Bosh sahifa"),
        ]
        await bot.set_my_commands(commands)
        log.info("bot_commands_registered")
    except Exception as e:
        log.warning("bot_commands_registration_failed", error=str(e))

    listen_port = settings.port
    try:
        if settings.webhook_url:
            # Production: Webhook rejimi
            webhook_path = "/webhook"
            full_webhook_url = settings.normalized_webhook_url
            log.info("setting_webhook", url=full_webhook_url, port=listen_port)

            await bot.set_webhook(
                url=full_webhook_url,
                secret_token=settings.webhook_secret or None,
            )

            webhook_handler = SimpleRequestHandler(
                dispatcher=dp,
                bot=bot,
                secret_token=settings.webhook_secret or None,
            )
            webhook_handler.register(app, path=webhook_path)
            setup_application(app, dp, bot=bot)

            site = web.TCPSite(runner, host="0.0.0.0", port=listen_port)
            await site.start()
            log.info("webhook_server_listening", port=listen_port)

            await asyncio.Event().wait()
        else:
            # Development / Polling rejimi (lekin /health va /metrics portda faol)
            site = web.TCPSite(runner, host="0.0.0.0", port=listen_port)
            await site.start()
            log.info("healthcheck_server_listening", port=listen_port)

            log.info("running_long_polling")
            await bot.delete_webhook(drop_pending_updates=False)
            await dp.start_polling(bot)

    finally:
        scheduler.shutdown()
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
