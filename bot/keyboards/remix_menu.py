"""FX selection submenu shown when a user taps 🎛️ Remix / FX."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.i18n import Translator
from bot.keyboards.callbacks import RemixCB, TrackActionCB


def remix_menu_kb(ref: str, _: Translator) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()

    def fx(label: str, code: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=label, callback_data=RemixCB(fx=code, ref=ref).pack()
        )

    b.row(fx("🌙 Nightcore", "nightcore"), fx("☀️ Daycore", "daycore"))
    b.row(fx("🌊 Slowed + Reverb", "slowed_reverb"), fx("💥 Bass Boost", "bass_boost"))
    b.row(fx("🎧 8D Audio", "8d"), fx("📻 Lo-Fi", "lofi"))
    b.row(fx("🎼 Karaoke", "karaoke"), fx("🎤 Vocals Only", "vocals_only"))
    b.row(
        fx("⚡ 0.75x", "speed_075"),
        fx("⚡ 1.25x", "speed_125"),
        fx("⚡ 1.5x", "speed_150"),
    )
    b.row(
        InlineKeyboardButton(
            text="✖️ " + _("btn-cancel"),
            callback_data=TrackActionCB(action="cancel", ref=ref).pack(),
        )
    )
    return b.as_markup()
