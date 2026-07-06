"""/settings — user preferences (currently: language)."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.i18n import Translator
from bot.keyboards.language_menu import language_kb

router = Router(name="settings")


@router.message(Command("settings"))
async def cmd_settings(message: Message, _: Translator) -> None:
    await message.answer(_("settings-language"), reply_markup=language_kb())


@router.message(Command("language"))
async def cmd_language(message: Message, _: Translator) -> None:
    await message.answer(_("settings-language"), reply_markup=language_kb())
