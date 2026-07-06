"""Entry point: builds every singleton, wires middlewares + routers, starts the
health server, and runs long-polling with a graceful shutdown.
"""
from __future__ import annotations

import asyncio

import aiohttp
import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from bot.config import settings
from bot.db.repository import Database
from bot.deps import Deps
from bot.health import build_health_app, start_health_server
from bot.logging_config import configure_logging
from bot.middlewares.analytics import AnalyticsMiddleware
from bot.middlewares.db import DatabaseMiddleware
from bot.middlewares.i18n import I18nMiddleware
from bot.middlewares.rate_limit import RateLimitMiddleware
from bot.routers import build_root_router
from bot.services.audio_source import AudioResolver
from bot.services.cover_generator import CoverGenerator
from bot.services.lyrics_service import LyricsService
from bot.services.search_aggregator import SearchAggregator

log = structlog.get_logger(__name__)


async def main() -> None:
    configure_logging(settings.log_level)
    log.info("starting", bot=settings.bot_username)

    # --- shared clients ---
    session = aiohttp.ClientSession()
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    db = Database()
    await db.create_all()

    deps = Deps(
        session=session,
        redis=redis,
        db=db,
        aggregator=SearchAggregator(session, redis),
        resolver=AudioResolver(session),
        cover=CoverGenerator(session),
        lyrics=LyricsService(redis),
    )

    # --- bot & dispatcher ---
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=RedisStorage(redis))
    dp["deps"] = deps  # injected into every handler by name

    # --- middlewares ---
    # Outer (per-update) DB session, then flood control, analytics, i18n.
    db_mw = DatabaseMiddleware(db)
    i18n_mw = I18nMiddleware()
    flood_mw = RateLimitMiddleware(redis, limit=3, window_sec=5)
    analytics_mw = AnalyticsMiddleware(redis)

    for observer in (dp.message, dp.callback_query, dp.inline_query):
        observer.outer_middleware(db_mw)
        observer.outer_middleware(i18n_mw)
        observer.middleware(flood_mw)
        observer.middleware(analytics_mw)

    dp.include_router(build_root_router())

    # --- health server ---
    health_app = build_health_app(redis, db)
    health_runner = await start_health_server(health_app, settings.healthcheck_port)

    # --- run ---
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)  # deps already registered via dp["deps"]
    finally:
        log.info("shutting down")
        await health_runner.cleanup()
        await bot.session.close()
        await session.close()
        await redis.aclose()
        await db.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
