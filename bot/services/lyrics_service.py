"""Lyrics fetching (Genius official API) with translation.

Genius is the primary and only network source here. `lyricsgenius` is a sync
client, so calls run in a thread executor. Results are cached in Redis for a
day. Translation uses deep-translator (Google backend) with auto source
detection.
"""
from __future__ import annotations

import asyncio

import structlog
from redis.asyncio import Redis

from bot.config import settings

log = structlog.get_logger(__name__)

_TG_LIMIT = 4096
_CACHE_TTL = 86400


class LyricsService:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self._genius = None
        token = settings.genius_access_token.get_secret_value()
        if token:
            try:
                import lyricsgenius

                self._genius = lyricsgenius.Genius(
                    token,
                    timeout=10,
                    retries=2,
                    remove_section_headers=False,
                    verbose=False,
                )
                self._genius._session.headers["User-Agent"] = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            except Exception as exc:  # pragma: no cover
                log.warning("genius-init-failed", error=str(exc))

    async def get_lyrics(self, artist: str, title: str) -> str | None:
        cache_key = f"lyrics:{artist}:{title}".lower()
        if cached := await self.redis.get(cache_key):
            text = cached.decode() if isinstance(cached, bytes) else cached
            return text or None

        text = await self._fetch_genius(artist, title)
        # Cache even a miss (empty string) briefly to avoid hammering the API.
        await self.redis.set(cache_key, text or "", ex=_CACHE_TTL if text else 900)
        return text

    async def _fetch_genius(self, artist: str, title: str) -> str | None:
        if self._genius is None:
            return None
        loop = asyncio.get_running_loop()
        try:
            song = await loop.run_in_executor(
                None, lambda: self._genius.search_song(title, artist)
            )
        except Exception as exc:  # pragma: no cover - network
            log.warning("genius-search-failed", error=str(exc))
            return None
        if song is None or not song.lyrics:
            return None
        return _clean(song.lyrics)

    async def translate(self, text: str, target_lang: str) -> str | None:
        loop = asyncio.get_running_loop()
        try:
            from deep_translator import GoogleTranslator

            def _do() -> str:
                translator = GoogleTranslator(source="auto", target=target_lang)
                # deep-translator caps single calls ~5000 chars; chunk to be safe.
                return "\n".join(
                    translator.translate(chunk) for chunk in _chunks(text, 4500)
                )

            return await loop.run_in_executor(None, _do)
        except Exception as exc:  # pragma: no cover
            log.warning("translate-failed", error=str(exc))
            return None


def paginate_text(text: str, limit: int = _TG_LIMIT) -> list[str]:
    """Split long lyrics into <=limit chunks on line boundaries."""
    pages: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > limit:
            if current:
                pages.append(current)
            # A single over-long line (rare) is hard-split.
            while len(line) > limit:
                pages.append(line[:limit])
                line = line[limit:]
            current = line
        else:
            current += line
    if current:
        pages.append(current)
    return pages or [text]


def _clean(lyrics: str) -> str:
    """Strip Genius' trailing 'NNNEmbed' cruft and leading title line."""
    lines = lyrics.splitlines()
    if lines and lines[0].lower().endswith("lyrics"):
        lines = lines[1:]
    text = "\n".join(lines).strip()
    # Remove a trailing "123Embed" / "Embed" token Genius appends.
    for token in ("Embed",):
        if text.endswith(token):
            text = text[: -len(token)].rstrip("0123456789").rstrip()
    return text


def _chunks(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [text]
