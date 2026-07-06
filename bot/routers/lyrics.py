"""Lyrics router: fetch via Genius, paginate, and offer translation."""
from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.deps import Deps
from bot.i18n import Translator
from bot.keyboards.callbacks import LyricsCB, TrackActionCB
from bot.services.lyrics_service import paginate_text
from bot.services.types import Track

router = Router(name="lyrics")
log = structlog.get_logger(__name__)


def _translate_kb(ref: str, _: Translator):
    b = InlineKeyboardBuilder()
    b.button(
        text="🔤 " + _("btn-translate"),
        callback_data=LyricsCB(action="translate", ref=ref).pack(),
    )
    return b.as_markup()


async def _send_lyrics(
    message: Message, track: Track, text: str, ref: str, _: Translator, with_button: bool
) -> None:
    header = f"🎤 <b>{track.display}</b>\n\n"
    pages = paginate_text(header + text)
    for idx, page in enumerate(pages):
        is_last = idx == len(pages) - 1
        await message.answer(
            page,
            reply_markup=_translate_kb(ref, _) if (is_last and with_button) else None,
            disable_web_page_preview=True,
        )


@router.callback_query(TrackActionCB.filter(F.action == "lyrics"))
async def on_lyrics(
    query: CallbackQuery, callback_data: TrackActionCB, deps: Deps, _: Translator
) -> None:
    track = await deps.aggregator.get_track(callback_data.ref)
    if track is None:
        await query.answer(_("track-unavailable"), show_alert=True)
        return
    await query.answer(_("loading"))
    text = await deps.lyrics.get_lyrics(track.artist, track.title)
    if not text:
        await query.answer(_("lyrics-not-found"), show_alert=True)
        return
    assert query.message is not None
    await _send_lyrics(query.message, track, text, track.ref, _, with_button=True)


@router.callback_query(LyricsCB.filter(F.action == "translate"))
async def on_translate(
    query: CallbackQuery, callback_data: LyricsCB, deps: Deps, lang: str, _: Translator
) -> None:
    track = await deps.aggregator.get_track(callback_data.ref)
    if track is None:
        await query.answer(_("track-unavailable"), show_alert=True)
        return
    await query.answer(_("translating"))
    original = await deps.lyrics.get_lyrics(track.artist, track.title)
    if not original:
        await query.answer(_("lyrics-not-found"), show_alert=True)
        return
    translated = await deps.lyrics.translate(original, lang)
    if not translated:
        await query.answer(_("translate-failed"), show_alert=True)
        return
    assert query.message is not None
    header = f"🎤 <b>{track.display}</b> — {lang.upper()}\n\n"
    for page in paginate_text(header + translated):
        await query.message.answer(page, disable_web_page_preview=True)
