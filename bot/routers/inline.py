"""Inline mode: `@YourMusicBot <query>` in any chat.

Returns up to 10 previewable results as InlineQueryResultAudio (Telegram plays
the 30-second preview inline). Tracks without a legal preview URL are skipped
here rather than served, keeping inline mode preview-only by construction.
"""
from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultAudio,
    InputTextMessageContent,
)

from bot.config import settings
from bot.deps import Deps

router = Router(name="inline")
log = structlog.get_logger(__name__)


@router.inline_query()
async def on_inline(query: InlineQuery, deps: Deps) -> None:
    text = query.query.strip()
    if not text:
        await query.answer([], cache_time=5, is_personal=True)
        return

    tracks = await deps.aggregator.search(text, limit=25)
    results: list[InlineQueryResultAudio] = []
    for t in tracks:
        if not t.preview_url:
            continue  # inline mode serves previews only
        results.append(
            InlineQueryResultAudio(
                id=t.ref[:64],
                audio_url=t.preview_url,
                title=f"{t.source.badge} {t.title}",
                performer=f"{t.artist} · {t.duration_str}",
                caption=(
                    f"🎵 {t.display}\n{settings.promo_caption_line}"
                ),
                input_message_content=None,
            )
        )
        if len(results) >= 10:
            break

    if not results:
        # Nothing previewable — offer a single hint article.
        from aiogram.types import InlineQueryResultArticle

        results_art = [
            InlineQueryResultArticle(
                id="none",
                title="No previewable results",
                description="Open the bot to search the full catalog.",
                input_message_content=InputTextMessageContent(
                    message_text=f"🔎 {text}\nSearch with @{settings.bot_username}"
                ),
            )
        ]
        await query.answer(results_art, cache_time=10, is_personal=True)
        return

    await query.answer(results, cache_time=30, is_personal=True)
