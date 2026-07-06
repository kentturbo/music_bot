"""Injects a per-user `Translator` (as `_`) into every handler's data dict.

Resolution order for the language:
  1. persisted preference in Postgres (users.language)
  2. the Telegram client's language_code
  3. the configured default
The DB middleware must run *before* this one so `data["repo"]` exists.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from bot.db.repository import Repo
from bot.i18n import i18n


class I18nMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: User | None = data.get("event_from_user")
        repo: Repo | None = data.get("repo")

        lang: str | None = None
        if tg_user and repo:
            lang = await repo.get_language(tg_user.id)
        if not lang and tg_user:
            lang = tg_user.language_code

        translator = i18n.get(lang or "")
        data["_"] = translator
        data["lang"] = translator.lang
        return await handler(event, data)
