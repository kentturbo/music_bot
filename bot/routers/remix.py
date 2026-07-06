"""Remix / FX router.

Tapping 🎛️ opens the FX submenu. Choosing an effect resolves the source audio,
applies the FX (light effects inline; heavy ones offloaded to Celery), and
re-delivers the remixed track with a fresh cover + promo tag.
"""
from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.db.repository import Repo
from bot.deps import Deps
from bot.i18n import Translator
from bot.keyboards.callbacks import RemixCB, TrackActionCB
from bot.keyboards.remix_menu import remix_menu_kb
from bot.services.audio_fx import HEAVY_FX
from bot.services.delivery import deliver_track

router = Router(name="remix")
log = structlog.get_logger(__name__)


@router.callback_query(TrackActionCB.filter(F.action == "remix"))
async def open_remix_menu(
    query: CallbackQuery, callback_data: TrackActionCB, _: Translator
) -> None:
    await query.answer()
    if isinstance(query.message, Message):
        await query.message.reply(
            _("remix-choose"), reply_markup=remix_menu_kb(callback_data.ref, _)
        )


@router.callback_query(TrackActionCB.filter(F.action == "cancel"))
async def cancel_remix(query: CallbackQuery) -> None:
    await query.answer()
    if isinstance(query.message, Message):
        try:
            await query.message.delete()
        except Exception:  # noqa: BLE001
            pass


@router.callback_query(RemixCB.filter())
async def apply_remix(
    query: CallbackQuery,
    callback_data: RemixCB,
    deps: Deps,
    repo: Repo,
    _: Translator,
) -> None:
    track = await deps.aggregator.get_track(callback_data.ref)
    if track is None:
        await query.answer(_("track-unavailable"), show_alert=True)
        return

    heavy = callback_data.fx in HEAVY_FX
    await query.answer()
    assert query.message is not None
    status = await query.message.reply(
        _("processing-heavy") if heavy else _("processing")
    )

    try:
        # The heavy path could be dispatched to Celery (see workers/fx_worker.py);
        # here we run it via the shared delivery pipeline which offloads the DSP
        # to a thread executor either way.
        await deliver_track(
            query.bot,
            query.message.chat.id,
            track,
            deps,
            repo,
            _,
            fx=callback_data.fx,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("remix-failed", fx=callback_data.fx, error=str(exc))
        await status.edit_text(_("error-generic"))
        return

    try:
        await status.delete()
    except Exception:  # noqa: BLE001
        pass
