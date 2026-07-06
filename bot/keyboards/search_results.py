"""Paginated search-results keyboard (5 tracks per page)."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.i18n import Translator
from bot.keyboards.callbacks import PageCB, SelectTrackCB
from bot.services.types import Track

PAGE_SIZE = 5


def results_kb(
    page_tracks: list[Track],
    token: str,
    page: int,
    total_pages: int,
    _: Translator,
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()

    for t in page_tracks:
        hq = " [HQ]" if t.bitrate >= 256 else ""
        b.row(
            InlineKeyboardButton(
                text=f"{t.source.badge} {t.display} ({t.duration_str}){hq}",
                callback_data=SelectTrackCB(ref=t.ref).pack(),
            )
        )

    # Navigation row (only the arrows that make sense).
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="◀ " + _("nav-prev"),
                callback_data=PageCB(token=token, page=page - 1).pack(),
            )
        )
    nav.append(
        InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data=PageCB(token=token, page=page).pack(),  # no-op refresh
        )
    )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                text=_("nav-next") + " ▶",
                callback_data=PageCB(token=token, page=page + 1).pack(),
            )
        )
    if nav:
        b.row(*nav)

    return b.as_markup()
