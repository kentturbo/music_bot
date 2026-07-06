"""Chat search: any non-command text is treated as a query.

Results are cached in Redis behind a short token so pagination callbacks stay
well under Telegram's 64-byte callback_data limit.
"""
from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.db.repository import Repo
from bot.deps import Deps
from bot.i18n import Translator
from bot.keyboards.callbacks import PageCB, SelectTrackCB
from bot.keyboards.search_results import results_kb
from bot.services.delivery import deliver_track
from bot.services.result_paging import (
    load_results,
    page_slice,
    store_results,
    total_pages,
)

router = Router(name="search")
log = structlog.get_logger(__name__)


@router.message(F.text & ~F.text.startswith("/"))
async def on_text_search(
    message: Message, deps: Deps, _: Translator
) -> None:
    query = (message.text or "").strip()
    if not query:
        return

    status = await message.answer(_("searching"))
    try:
        tracks = await deps.aggregator.search(query)
    except Exception as exc:  # noqa: BLE001
        log.error("search-failed", error=str(exc))
        await status.edit_text(_("error-generic"))
        return

    if not tracks:
        await status.edit_text(_("no-results", query=query))
        return

    # Cache every track individually so button handlers can always resolve them.
    for t in tracks:
        await deps.aggregator.cache_track(t)

    token = await store_results(deps.redis, tracks)
    total = total_pages(len(tracks))
    await status.edit_text(
        _("results-header", query=query, count=len(tracks)),
        reply_markup=results_kb(page_slice(tracks, 0), token, 0, total, _),
    )


@router.callback_query(PageCB.filter())
async def on_page(
    query: CallbackQuery, callback_data: PageCB, deps: Deps, _: Translator
) -> None:
    tracks = await load_results(deps.redis, callback_data.token)
    if not tracks:
        await query.answer(_("results-expired"), show_alert=True)
        return
    total = total_pages(len(tracks))
    page = max(0, min(callback_data.page, total - 1))
    if isinstance(query.message, Message):
        await query.message.edit_reply_markup(
            reply_markup=results_kb(page_slice(tracks, page), callback_data.token, page, total, _)
        )
    await query.answer()


@router.callback_query(SelectTrackCB.filter())
async def on_select(
    query: CallbackQuery,
    callback_data: SelectTrackCB,
    deps: Deps,
    repo: Repo,
    _: Translator,
) -> None:
    await query.answer(_("delivering"))
    track = await deps.aggregator.get_track(callback_data.ref)
    if track is None:
        await query.answer(_("track-unavailable"), show_alert=True)
        return
    await deps.aggregator.cache_track(track)  # keep it resolvable for actions
    assert query.message is not None
    await deliver_track(query.bot, query.message.chat.id, track, deps, repo, _)
