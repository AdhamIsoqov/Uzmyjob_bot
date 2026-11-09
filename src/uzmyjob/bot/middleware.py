"""Anti-flood ThrottlingMiddleware."""
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message

from uzmyjob.utils.metrics import THROTTLED_REQUESTS_TOTAL


class ThrottlingMiddleware(BaseMiddleware):
    """Har foydalanuvchi uchun rate-limit (msg/min)."""

    def __init__(self, rate: int = 30):
        self.rate = rate  # msg per minute
        self._user_timestamps: dict[int, list[float]] = {}

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id if event.from_user else 0
        now = time.time()
        window = 60.0

        timestamps = self._user_timestamps.setdefault(user_id, [])
        # Eskilarni tozala
        self._user_timestamps[user_id] = [t for t in timestamps if now - t < window]

        if len(self._user_timestamps[user_id]) >= self.rate:
            THROTTLED_REQUESTS_TOTAL.inc()
            await event.answer("⚠️ Juda tez yuboryapsiz. Biroz kuting.")
            return

        self._user_timestamps[user_id].append(now)
        return await handler(event, data)
