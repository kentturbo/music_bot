"""Application-wide singletons, built once at startup and injected into every
handler as `deps` via the dispatcher's workflow data.
"""
from __future__ import annotations

from dataclasses import dataclass

import aiohttp
from redis.asyncio import Redis

from bot.db.repository import Database
from bot.services.audio_source import AudioResolver
from bot.services.cover_generator import CoverGenerator
from bot.services.lyrics_service import LyricsService
from bot.services.search_aggregator import SearchAggregator


@dataclass
class Deps:
    session: aiohttp.ClientSession
    redis: Redis
    db: Database
    aggregator: SearchAggregator
    resolver: AudioResolver
    cover: CoverGenerator
    lyrics: LyricsService
