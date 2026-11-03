"""Prometheus metrikalari eksport moduli."""
from prometheus_client import Counter, Gauge, start_http_server

from uzmyjob.utils.logger import log

# Metrikalar
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


def start_prometheus_metrics_server(port: int = 8000) -> None:
    """Prometheus /metrics endpointi uchun HTTP server ishga tushirish."""
    try:
        start_http_server(port)
        log.info("prometheus_server_started", port=port)
    except Exception as e:
        log.warning("prometheus_server_start_failed", error=str(e))
