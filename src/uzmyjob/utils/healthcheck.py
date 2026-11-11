"""Tizim salomatligi va resurslar nazorati (Healthcheck)."""
import asyncio
import json
import sys
import tracemalloc
from typing import Any

from sqlalchemy import text

from uzmyjob.models.base import AsyncSessionLocal
from uzmyjob.utils.logger import log


def _get_memory_mb() -> float:
    """Joriy yoki tracemalloc xotira sarfini MB da qaytaradi."""
    if tracemalloc.is_tracing():
        current, _peak = tracemalloc.get_traced_memory()
        return round(current / (1024 * 1024), 2)
    try:
        import resource

        # Linuxda maxrss KB da, macOS da baytda
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
        return round(rss / divisor, 2)
    except Exception:
        return 0.0


async def run_healthcheck() -> dict[str, Any]:
    """
    Tizim sog'lomligini tekshirish:
    1. Ma'lumotlar bazasi ulanishi
    2. Xotira sarfi (< 300 MB)
    """
    report: dict[str, Any] = {
        "status": "healthy",
        "database": "unknown",
        "memory_mb": 0.0,
        "errors": [],
    }

    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("SELECT 1"))
            if res.scalar() == 1:
                report["database"] = "connected"
    except Exception as exc:
        log.error("healthcheck_db_error", error=str(exc))
        report["status"] = "unhealthy"
        report["database"] = "disconnected"
        report["errors"].append("Database connection failed")

    mem_mb = _get_memory_mb()
    report["memory_mb"] = mem_mb
    if mem_mb > 300.0:
        report["status"] = "unhealthy"
        report["errors"].append(f"Memory usage exceeded limit: {mem_mb} MB > 300 MB")

    return report


if __name__ == "__main__":
    tracemalloc.start()
    result = asyncio.run(run_healthcheck())
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "healthy" else 1)
