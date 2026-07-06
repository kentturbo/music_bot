"""Opens one DB session per update and injects a `Repo` as `data["repo"]`.

Registered as an outer middleware so it wraps the whole handler chain and the
session is guaranteed to close afterwards.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.db.repository import Database


class DatabaseMiddleware(BaseMiddleware):
    def __init__(self, db: Database) -> None:
        self.db = db

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.db.repo() as repo:
            data["repo"] = repo
            return await handler(event, data)
