"""Router registry — imported by main.py to include every router in order."""
from __future__ import annotations

from aiogram import Router

from bot.routers import (
    inline,
    lyrics,
    remix,
    search,
    settings,
    start,
    track,
)


def build_root_router() -> Router:
    root = Router(name="root")
    # Order matters: specific commands/callbacks before the catch-all search.
    root.include_router(start.router)
    root.include_router(settings.router)
    root.include_router(track.router)
    root.include_router(remix.router)
    root.include_router(lyrics.router)
    root.include_router(inline.router)
    root.include_router(search.router)  # text catch-all last
    return root
