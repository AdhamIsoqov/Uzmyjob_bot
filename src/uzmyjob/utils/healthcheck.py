"""Tizim salomatligi va resurslar nazorati (Healthcheck & Watchdog)."""
import asyncio
import json
import sys
import tracemalloc

from sqlalchemy import text

from uzmyjob.models.base import AsyncSessionLocal


async def run_healthcheck() -> dict:
    """
    Tizim sog'lomligini tekshirish:
    1. PostgreSQL DB ulanishi
    2. Xotira sarfi (memory < 300 MB)
    """
    report = {
        "status": "healthy",
        "database": "unknown",
        "memory_mb": 0.0,
        "errors": [],
    }

    # 1. DB tekshirish
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("SELECT 1"))
            val = res.scalar()
            if val == 1:
                report["database"] = "connected"
    except Exception as e:
        report["status"] = "unhealthy"
        report["database"] = "disconnected"
        report["errors"].append(f"DB xatosi: {e!s}")

    # 2. Xotira tekshirish
    try:
        _current, peak = tracemalloc.get_traced_memory()
        mem_mb = peak / (1024 * 1024)
        report["memory_mb"] = round(mem_mb, 2)
        if mem_mb > 300.0:
            report["status"] = "unhealthy"
            report["errors"].append(f"Xotira me'yordan oshdi: {mem_mb} MB > 300 MB")
    except Exception:
        report["memory_mb"] = 0.0

    return report


if __name__ == "__main__":
    tracemalloc.start()
    result = asyncio.run(run_healthcheck())
    print(json.dumps(result, indent=2))
    if result["status"] != "healthy":
        sys.exit(1)
    sys.exit(0)
