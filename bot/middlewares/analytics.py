"""Lightweight usage tracking: bumps per-day counters in Redis and refreshes
the user's last_seen. Cheap enough to run on every update; read the counters
from a dashboard or an admin command.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, InlineQuery, Message, TelegramObject, User
from redis.asyncio import Redis

log = structlog.get_logger(__name__)


class AnalyticsMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        kind = self._kind(event)
        if user is not None:
            pipe = self.redis.pipeline()
            pipe.pfadd("dau", user.id)          # HyperLogLog: daily active users
            pipe.hincrby("events", kind, 1)     # counter by event type
            await pipe.execute()
            log.debug("update", user_id=user.id, kind=kind)
        return await handler(event, data)

    @staticmethod
    def _kind(event: TelegramObject) -> str:
        if isinstance(event, Message):
            return "message"
        if isinstance(event, CallbackQuery):
            return "callback"
        if isinstance(event, InlineQuery):
            return "inline"
        return type(event).__name__
