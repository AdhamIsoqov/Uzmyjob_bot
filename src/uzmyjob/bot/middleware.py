"""Anti-flood ThrottlingMiddleware."""

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from uzmyjob.utils.metrics import THROTTLED_REQUESTS_TOTAL


class ThrottlingMiddleware(BaseMiddleware):
    """Har foydalanuvchi uchun rate-limit (so'rov/daqiqa)."""

    def __init__(self, rate: int = 30, window: float = 60.0):
        self.rate = rate
        self.window = window
        self._user_timestamps: dict[int, list[float]] = {}
        self._last_cleanup: float = time.monotonic()

    def _evict_expired(self, now: float) -> None:
        """Muddati o'tgan timestamp va bo'sh yozuvlarni xotiradan tozalash."""
        stale_users: list[int] = []
        for uid, ts_list in self._user_timestamps.items():
            active = [t for t in ts_list if now - t < self.window]
            if active:
                self._user_timestamps[uid] = active
            else:
                stale_users.append(uid)
        for uid in stale_users:
            del self._user_timestamps[uid]
        self._last_cleanup = now

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        user_id = from_user.id if from_user else 0
        now = time.monotonic()

        if now - self._last_cleanup >= self.window:
            self._evict_expired(now)

        timestamps = [
            t for t in self._user_timestamps.get(user_id, []) if now - t < self.window
        ]

        if len(timestamps) >= self.rate:
            self._user_timestamps[user_id] = timestamps
            THROTTLED_REQUESTS_TOTAL.inc()
            warning_text = "⚠️ Juda tez yuboryapsiz. Biroz kuting."
            if isinstance(event, CallbackQuery):
                await event.answer(warning_text, show_alert=False)
            elif isinstance(event, Message):
                await event.answer(warning_text)
            return None

        timestamps.append(now)
        self._user_timestamps[user_id] = timestamps
        return await handler(event, data)
