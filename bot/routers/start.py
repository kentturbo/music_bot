"""/start onboarding, /help, and the initial language picker."""
from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.db.repository import Repo
from bot.i18n import Translator, i18n
from bot.keyboards.callbacks import LangCB
from bot.keyboards.language_menu import language_kb

router = Router(name="start")
log = structlog.get_logger(__name__)

# A cheerful welcome sticker (a well-known public sticker file_id). Swap for
# your own via BotFather if you prefer branded art.
WELCOME_STICKER = "CAACAgIAAxkBAAEBQmVk8wAB... "  # replace with a real file_id


@router.message(CommandStart())
async def cmd_start(message: Message, repo: Repo, _: Translator) -> None:
    user = message.from_user
    assert user is not None
    await repo.upsert_user(user.id, user.username, user.language_code)

    # Best-effort welcome sticker; ignore if the placeholder id is invalid.
    try:
        await message.answer_sticker(WELCOME_STICKER.strip())
    except Exception:  # noqa: BLE001 - sticker is decorative only
        pass

    await message.answer(
        _("welcome", name=user.first_name or "friend"),
        reply_markup=_example_and_lang_kb(_),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, _: Translator) -> None:
    await message.answer(_("help"))


@router.callback_query(LangCB.filter())
async def on_language_pick(
    query: CallbackQuery, callback_data: LangCB, repo: Repo
) -> None:
    assert query.from_user is not None
    await repo.set_language(query.from_user.id, callback_data.code)
    translator = i18n.get(callback_data.code)
    await query.answer(translator("language-set"))
    if isinstance(query.message, Message):
        await query.message.edit_text(
            translator("welcome", name=query.from_user.first_name or "friend"),
            reply_markup=_example_and_lang_kb(translator),
        )


def _example_and_lang_kb(_: Translator):
    """Language buttons + three example search queries the user can tap."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    b = InlineKeyboardBuilder()
    # Example queries are sent back as switch_inline_query_current_chat so
    # tapping pre-fills the chat input with a ready search.
    from aiogram.types import InlineKeyboardButton

    for q in ("Daft Punk", "The Weeknd Blinding Lights", "lofi hip hop"):
        b.row(
            InlineKeyboardButton(
                text=f"🔎 {q}", switch_inline_query_current_chat=q
            )
        )
    # Merge in the language grid.
    for row in language_kb().inline_keyboard:
        b.row(*row)
    return b.as_markup()
