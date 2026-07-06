"""Shared helpers for storing a result set in Redis behind a short token and
rendering paginated result keyboards. Used by search + discovery routers.
"""
from __future__ import annotations

import json
import secrets

from redis.asyncio import Redis

from bot.keyboards.search_results import PAGE_SIZE
from bot.services.types import Track, track_from_dict, track_to_dict

_RESULTS_TTL = 3600


async def store_results(redis: Redis, tracks: list[Track]) -> str:
    token = secrets.token_urlsafe(6)
    await redis.set(
        f"results:{token}",
        json.dumps([track_to_dict(t) for t in tracks]),
        ex=_RESULTS_TTL,
    )
    return token


async def load_results(redis: Redis, token: str) -> list[Track]:
    raw = await redis.get(f"results:{token}")
    if not raw:
        return []
    return [track_from_dict(d) for d in json.loads(raw)]


def page_slice(tracks: list[Track], page: int) -> list[Track]:
    start = page * PAGE_SIZE
    return tracks[start : start + PAGE_SIZE]


def total_pages(n: int) -> int:
    return max(1, (n + PAGE_SIZE - 1) // PAGE_SIZE)
