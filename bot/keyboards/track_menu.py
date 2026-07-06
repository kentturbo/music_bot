"""The inline action keyboard attached to every delivered audio message."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.i18n import Translator
from bot.keyboards.callbacks import TrackActionCB
from bot.services.types import Track


def track_action_kb(track: Track, _: Translator, liked: bool = False) -> InlineKeyboardMarkup:
    ref = track.ref
    b = InlineKeyboardBuilder()

    b.row(
        InlineKeyboardButton(
            text=("❤️ " + _("btn-liked")) if liked else ("🤍 " + _("btn-like")),
            callback_data=TrackActionCB(action="like", ref=ref).pack(),
        ),
        InlineKeyboardButton(
            text="➕ " + _("btn-playlist"),
            callback_data=TrackActionCB(action="playlist", ref=ref).pack(),
        ),
        InlineKeyboardButton(
            text="📤 " + _("btn-share"),
            callback_data=TrackActionCB(action="share", ref=ref).pack(),
        ),
    )
    b.row(
        InlineKeyboardButton(
            text="🎵 " + _("btn-similar"),
            callback_data=TrackActionCB(action="similar", ref=ref).pack(),
        )
    )
    b.row(
        InlineKeyboardButton(
            text="👤 " + _("btn-more-by", artist=_short(track.artist)),
            callback_data=TrackActionCB(action="artist", ref=ref).pack(),
        )
    )
    if track.album:
        b.row(
            InlineKeyboardButton(
                text="💿 " + _short(track.album),
                callback_data=TrackActionCB(action="album", ref=ref).pack(),
            )
        )
    b.row(
        InlineKeyboardButton(
            text="🎤 " + _("btn-lyrics"),
            callback_data=TrackActionCB(action="lyrics", ref=ref).pack(),
        ),
        InlineKeyboardButton(
            text="🎛️ " + _("btn-remix"),
            callback_data=TrackActionCB(action="remix", ref=ref).pack(),
        ),
    )
    b.row(
        InlineKeyboardButton(
            text="⬇️ " + _("btn-download"),
            callback_data=TrackActionCB(action="download", ref=ref).pack(),
        ),
        InlineKeyboardButton(
            text="📊 " + _("btn-quality"),
            callback_data=TrackActionCB(action="quality", ref=ref).pack(),
        ),
    )
    return b.as_markup()


def _short(text: str, n: int = 20) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"
