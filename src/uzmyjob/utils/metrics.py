"""Prometheus metrikalari eksport moduli."""
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from sqlalchemy import func, select

from uzmyjob.models.base import AsyncSessionLocal
from uzmyjob.models.user import User
from uzmyjob.utils.logger import log

# Vakansiyalar va arizalar
VACANCIES_FETCHED = Counter(
    "uzmyjob_vacancies_fetched_total",
    "Jami olingan vakansiyalar soni",
    ["source"],
)

APPLICATIONS_SENT = Counter(
    "uzmyjob_applications_sent_total",
    "Yuborilgan arizalar soni",
    ["source", "status"],
)

ACTIVE_USERS = Gauge(
    "uzmyjob_active_users_total",
    "Tizimdan foydalanayotgan faol foydalanuvchilar soni",
)

# M4: Kengaytirilgan metrikalar
DEDUPLICATED_TOTAL = Counter(
    "uzmyjob_deduplicated_total",
    "Deduplikatsiya qilingan (tashlab ketilgan) dublikat vakansiyalar soni",
    ["reason"],  # "source_id", "content_hash", "fuzzy"
)

LLM_RERANK_CALLS_TOTAL = Counter(
    "uzmyjob_llm_rerank_calls_total",
    "Gemini Flash LLM re-ranker ga qilingan so'rovlar soni",
    ["status"],  # "success", "cost_limited", "error"
)

LLM_COST_DOLLARS_TOTAL = Counter(
    "uzmyjob_llm_cost_dollars_total",
    "Gemini Flash re-rank uchun sarflangan taxminiy dollar qiymati",
)

MATCHING_DURATION_SECONDS = Histogram(
    "uzmyjob_matching_duration_seconds",
    "Bitta vakansiyani moslashtirish vaqti (soniyalarda)",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0],
)

SOURCE_ERRORS_TOTAL = Counter(
    "uzmyjob_source_errors_total",
    "Manbalardan ma'lumot olishda yuz bergan xatoliklar",
    ["source"],
)

THROTTLED_REQUESTS_TOTAL = Counter(
    "uzmyjob_throttled_requests_total",
    "ThrottlingMiddleware tomonidan cheklangan Telegram so'rovlari",
)


async def update_system_gauges() -> None:
    """Tizim dinamik metrikalarini (masalan faol foydalanuvchilar) yangilash."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(func.count()).select_from(User).where(User.is_active.is_(True))
            count = (await session.execute(stmt)).scalar() or 0
            ACTIVE_USERS.set(count)
    except Exception as e:
        log.warning("metrics_gauge_update_failed", error=str(e))


def start_prometheus_metrics_server(port: int = 8000) -> None:
    """Prometheus /metrics endpointi uchun HTTP server ishga tushirish."""
    try:
        start_http_server(port)
        log.info("prometheus_server_started", port=port)
    except Exception as e:
        log.warning("prometheus_server_start_failed", error=str(e))
