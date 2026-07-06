"""Track delivery pipeline, shared by search / similar / remix routers.

Steps:
  1. Reuse a cached Telegram file_id if we've sent this (track, fx) before.
  2. Otherwise resolve audio bytes (licensed backend or legal preview).
  3. Build/embed cover, write ID3 tags + promo, apply FX if requested.
  4. Send as audio with the per-track action keyboard; cache the file_id.

Everything degrades gracefully: no audio source -> a friendly "preview only"
notice instead of a crash.
"""
from __future__ import annotations

import structlog
from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, URLInputFile

from bot.config import settings
from bot.db.repository import Repo
from bot.deps import Deps
from bot.i18n import Translator
from bot.keyboards.track_menu import track_action_kb
from bot.services.audio_fx import FX_LABELS, apply_fx
from bot.services.audio_source import _stream
from bot.services.promo_tagger import tag_audio
from bot.services.types import Track

log = structlog.get_logger(__name__)


def _caption(track: Track, _: Translator, is_preview: bool, fmt: str, bitrate: int) -> str:
    parts = [f"🎵 <b>{track.display}</b>"]
    meta = " | ".join(x for x in (track.album, track.year) if x)
    if meta:
        parts.append(f"💿 {meta}")
    if bitrate:
        parts.append(f"🔊 {bitrate}kbps {fmt.upper()}")
    if is_preview:
        parts.append("⏱ " + _("preview-notice"))
    parts.append(settings.promo_caption_line)
    return "\n".join(parts)


async def deliver_track(
    bot: Bot,
    chat_id: int,
    track: Track,
    deps: Deps,
    repo: Repo,
    _: Translator,
    fx: str | None = None,
) -> None:
    fx_key = fx or "original"
    title = track.title
    if fx:
        title = f"[{FX_LABELS.get(fx, fx)}] {track.title}"

    # 1) file_id reuse — instant resend.
    if cached_id := await repo.get_cached_file(track.ref, fx_key):
        await bot.send_audio(
            chat_id,
            audio=cached_id,
            caption=_caption(track, _, is_preview=False, fmt="mp3", bitrate=track.bitrate),
            title=title,
            performer=track.artist,
            reply_markup=track_action_kb(track, _),
        )
        return

    # 2) resolve audio.
    result = await deps.resolver.resolve(track)
    if result is None:
        await bot.send_message(chat_id, _("no-audio-source"))
        return

    audio_bytes = result.data
    src_fmt = result.ext

    # 3) If VK gave us a direct URL and NO FX is requested, stream it straight to Telegram (no download needed).
    if result.url and audio_bytes is None:
        if fx:
            # We need the actual bytes to apply FX, so download the URL first.
            audio_bytes = await _stream(deps.session, result.url)
            if audio_bytes is None:
                await bot.send_message(chat_id, _("no-audio-source"))
                return
        else:
            sent = await bot.send_audio(
                chat_id,
                audio=URLInputFile(result.url, filename=f"{track.artist} - {title}.mp3"),
                caption=_caption(
                    track, _, is_preview=False, fmt=src_fmt, bitrate=result.bitrate
                ),
                title=title,
                performer=track.artist,
                duration=track.duration or None,
                reply_markup=track_action_kb(track, _),
            )
            # Cache the Telegram file_id so future requests are instant resends.
            if sent.audio:
                await repo.store_cached_file(track.ref, sent.audio.file_id, fx_key)
            return

    # 4) FX on downloaded bytes.
    if fx:
        audio_bytes = await apply_fx(audio_bytes, fx, src_format=src_fmt)
        src_fmt = "mp3"

    # cover + tags + promo.
    cover_jpeg = await deps.cover.get_cover(track.artist, track.title, track.cover_url)
    tagged = tag_audio(audio_bytes, track, cover_jpeg, title_override=title)

    filename = f"{track.artist} - {title}.{src_fmt}".replace("/", "_")
    sent = await bot.send_audio(
        chat_id,
        audio=BufferedInputFile(tagged, filename=filename),
        thumbnail=BufferedInputFile(cover_jpeg, filename="cover.jpg"),
        caption=_caption(
            track, _, is_preview=result.is_preview, fmt=src_fmt, bitrate=result.bitrate
        ),
        title=title,
        performer=track.artist,
        duration=track.duration or None,
        reply_markup=track_action_kb(track, _),
    )

    # 5) cache the file_id for instant future resends.
    if sent.audio:
        await repo.store_cached_file(track.ref, sent.audio.file_id, fx_key)


def with_liked_state(track: Track, _: Translator, liked: bool) -> InlineKeyboardMarkup:
    return track_action_kb(track, _, liked=liked)
