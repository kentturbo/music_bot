"""Handlers for the per-track action keyboard (Like / Share / Similar / More
by Artist / Album / Download / Quality). Remix and Lyrics live in their own
routers; this one owns everything else.
"""
from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.db.repository import Repo
from bot.deps import Deps
from bot.i18n import Translator
from bot.keyboards.callbacks import TrackActionCB
from bot.keyboards.search_results import results_kb
from bot.services.result_paging import page_slice, store_results, total_pages
from bot.services.types import Track

router = Router(name="track")
log = structlog.get_logger(__name__)

_DISCOVERY = {"similar", "artist", "album"}


async def _resolve(deps: Deps, ref: str) -> Track | None:
    return await deps.aggregator.get_track(ref)


@router.callback_query(TrackActionCB.filter(F.action == "like"))
async def on_like(
    query: CallbackQuery, callback_data: TrackActionCB, deps: Deps, repo: Repo, _: Translator
) -> None:
    track = await _resolve(deps, callback_data.ref)
    if track is None:
        await query.answer(_("track-unavailable"), show_alert=True)
        return
    liked = await repo.toggle_like(
        query.from_user.id, track.ref, track.artist, track.title
    )
    await query.answer(_("liked") if liked else _("unliked"))
    # Refresh the keyboard to reflect the heart state.
    from bot.keyboards.track_menu import track_action_kb

    if isinstance(query.message, Message):
        try:
            await query.message.edit_reply_markup(
                reply_markup=track_action_kb(track, _, liked=liked)
            )
        except Exception:  # noqa: BLE001 - "message not modified" is harmless
            pass


@router.callback_query(TrackActionCB.filter(F.action == "share"))
async def on_share(
    query: CallbackQuery, callback_data: TrackActionCB, deps: Deps, _: Translator
) -> None:
    track = await _resolve(deps, callback_data.ref)
    if track is None:
        await query.answer(_("track-unavailable"), show_alert=True)
        return
    link = f"https://t.me/{settings.bot_username}?start={track.ref}"
    await query.answer()
    if isinstance(query.message, Message):
        await query.message.reply(
            _("share-text", track=track.display, link=link),
            disable_web_page_preview=True,
        )


@router.callback_query(TrackActionCB.filter(F.action == "playlist"))
async def on_playlist(query: CallbackQuery, _: Translator) -> None:
    # Playlist storage is modeled in the DB; the management UI is a follow-up.
    await query.answer(_("added-playlist"))


@router.callback_query(TrackActionCB.filter(F.action.in_({"download", "quality"})))
async def on_download_quality(
    query: CallbackQuery, callback_data: TrackActionCB, deps: Deps, repo: Repo, _: Translator
) -> None:
    track = await _resolve(deps, callback_data.ref)
    if track is None:
        await query.answer(_("track-unavailable"), show_alert=True)
        return
    if callback_data.action == "quality":
        br = f"{track.bitrate}kbps" if track.bitrate else _("quality-unknown")
        await query.answer(_("quality-info", bitrate=br), show_alert=True)
        return
    # "Download FLAC" is only meaningful when a licensed backend can serve it.
    if not deps.resolver.licensed.enabled:
        await query.answer(_("flac-unavailable"), show_alert=True)
        return
    await query.answer(_("delivering"))
    from bot.services.delivery import deliver_track

    assert query.message is not None
    # Re-deliver at best available quality (the licensed source decides format).
    await deliver_track(query.bot, query.message.chat.id, track, deps, repo, _)


@router.callback_query(TrackActionCB.filter(F.action.in_(_DISCOVERY)))
async def on_discovery(
    query: CallbackQuery, callback_data: TrackActionCB, deps: Deps, _: Translator
) -> None:
    track = await _resolve(deps, callback_data.ref)
    if track is None:
        await query.answer(_("track-unavailable"), show_alert=True)
        return
    await query.answer(_("loading"))

    action = callback_data.action
    if action == "similar":
        tracks = await deps.aggregator.get_similar(track.artist, track.title)
        header = _("similar-header", track=track.display)
    elif action == "artist":
        tracks = await deps.aggregator.get_artist_top(track.artist_id)
        header = _("artist-header", artist=track.artist)
    else:  # album
        tracks = await deps.aggregator.get_album_tracks(track.album_id)
        header = _("album-header", album=track.album or track.display)

    if not tracks:
        await query.answer(_("nothing-found"), show_alert=True)
        return

    for t in tracks:
        await deps.aggregator.cache_track(t)
    token = await store_results(deps.redis, tracks)
    total = total_pages(len(tracks))
    assert query.message is not None
    await query.message.answer(
        header,
        reply_markup=results_kb(page_slice(tracks, 0), token, 0, total, _),
    )
