"""Redis-backed anti-flood: max N actions per window per user.

Uses a sliding fixed window via INCR + EXPIRE. On overflow the update is
dropped and the user gets one polite notice (throttled so we don't spam them).
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User
from redis.asyncio import Redis

from bot.i18n import Translator


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis, limit: int = 3, window_sec: int = 5) -> None:
        self.redis = redis
        self.limit = limit
        self.window = window_sec

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        key = f"flood:{user.id}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, self.window)

        if count > self.limit:
            # Notify at most once per window (the notice key expires with it).
            notice_key = f"flood:notice:{user.id}"
            if await self.redis.set(notice_key, 1, ex=self.window, nx=True):
                await self._warn(event, data.get("_"))
            return None  # drop the update

        return await handler(event, data)

    @staticmethod
    async def _warn(event: TelegramObject, _: Translator | None) -> None:
        text = _("flood-wait") if _ else "⏳ Slow down a moment, please."
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=False)
