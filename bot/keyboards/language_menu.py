"""Language picker keyboard."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.callbacks import LangCB

_LANGUAGES: list[tuple[str, str]] = [
    ("ru", "🇷🇺 Русский"),
    ("en", "🇬🇧 English"),
    ("de", "🇩🇪 Deutsch"),
    ("es", "🇪🇸 Español"),
    ("uk", "🇺🇦 Українська"),
    ("kk", "🇰🇿 Қазақша"),
]


def language_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for code, label in _LANGUAGES:
        b.button(text=label, callback_data=LangCB(code=code).pack())
    b.adjust(2)
    return b.as_markup()
