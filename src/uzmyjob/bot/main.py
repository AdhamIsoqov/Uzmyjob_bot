"""Bot kirish nuqtasi — aiogram 3, Webhook/Polling va APScheduler."""
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from uzmyjob.bot.handlers import hh_auth, start, stats, stop, vacancies, wizard
from uzmyjob.bot.middleware import ThrottlingMiddleware
from uzmyjob.config import settings
from uzmyjob.pipeline.pipeline import JobPipeline
from uzmyjob.utils.logger import log, setup_logging
from uzmyjob.utils.metrics import start_prometheus_metrics_server


async def scheduled_pipeline_job(pipeline: JobPipeline):
    """Har 15 daqiqada yangi vakansiyalarni tekshirish va xabardor qilish."""
    log.info("scheduled_pipeline_job_started")
    try:
        stats_res = await pipeline.run_once()
        log.info("scheduled_pipeline_job_finished", **stats_res)
    except Exception as e:
        log.error("scheduled_pipeline_job_error", error=str(e))


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
    dp.include_router(stats.router)
    dp.include_router(stop.router)
    dp.include_router(vacancies.router)
    dp.include_router(hh_auth.router)

    # Prometheus server
    start_prometheus_metrics_server(port=8000)

    # Background Pipeline Scheduler
    pipeline = JobPipeline(bot=bot)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_pipeline_job,
        "interval",
        minutes=settings.poll_interval_minutes,
        args=[pipeline],
        id="job_pipeline_interval",
    )
    scheduler.start()
    log.info("scheduler_started", interval_minutes=settings.poll_interval_minutes)

    try:
        if settings.webhook_url:
            # Production: Webhook rejimi
            webhook_path = "/webhook"
            full_webhook_url = f"{settings.webhook_url.rstrip('/')}{webhook_path}"
            log.info("setting_webhook", url=full_webhook_url)

            await bot.set_webhook(
                url=full_webhook_url,
                secret_token=settings.webhook_secret or None,
            )

            app = web.Application()
            webhook_handler = SimpleRequestHandler(
                dispatcher=dp,
                bot=bot,
                secret_token=settings.webhook_secret or None,
            )
            webhook_handler.register(app, path=webhook_path)
            setup_application(app, dp, bot=bot)

            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host="0.0.0.0", port=8080)
            await site.start()
            log.info("webhook_server_listening", port=8080)

            # Doimiy ishlash
            await asyncio.Event().wait()
        else:
            # Development: Long-polling rejimi
            log.info("running_long_polling")
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)

    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
