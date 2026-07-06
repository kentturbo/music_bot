"""Pydantic CallbackData factories.

Telegram limits callback_data to 64 bytes, so we keep payloads terse:
track refs are short (`deezer:12345`) and long queries are stored in Redis
behind a token rather than embedded.
"""
from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class SelectTrackCB(CallbackData, prefix="sel"):
    """Pick a track from a results list -> deliver it."""

    ref: str


class TrackActionCB(CallbackData, prefix="trk"):
    """A button on a delivered track's action keyboard."""

    action: str  # like | share | similar | artist | album | lyrics | remix | download | quality
    ref: str


class PageCB(CallbackData, prefix="pg"):
    """Paginate a stored result set (token -> Redis)."""

    token: str
    page: int


class RemixCB(CallbackData, prefix="fx"):
    """Choose an FX preset for a track."""

    fx: str
    ref: str


class LangCB(CallbackData, prefix="lang"):
    code: str


class LyricsCB(CallbackData, prefix="lyr"):
    action: str  # translate
    ref: str
