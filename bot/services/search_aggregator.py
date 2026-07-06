"""Multi-source *metadata* search with parallel fan-out, fuzzy dedup, ranking
and a Redis cache (1h TTL).

Legality note: every source below is queried for metadata (and, for Deezer,
the 30-second preview URL that Deezer publishes for exactly this purpose).
Full-track retrieval is delegated to `audio_source` and only happens through a
backend the operator is licensed to use.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict

import aiohttp
import structlog
from rapidfuzz import fuzz
from redis.asyncio import Redis

from bot.config import settings
from bot.services.types import Source, Track, normalize

log = structlog.get_logger(__name__)

_DEEZER_API = "https://api.deezer.com"
_LASTFM_API = "https://ws.audioscrobbler.com/2.0/"
_PER_SOURCE_TIMEOUT = 6.0  # seconds
_CACHE_TTL = 3600
_DEDUP_THRESHOLD = 88  # rapidfuzz score above which two results are "the same"


class SearchAggregator:
    def __init__(self, session: aiohttp.ClientSession, redis: Redis) -> None:
        self.session = session
        self.redis = redis
        # ytmusicapi is imported lazily & called in a thread (it is sync).
        try:
            from ytmusicapi import YTMusic

            self._ytmusic = YTMusic()
        except Exception as exc:  # pragma: no cover - optional dependency/network
            log.warning("ytmusic-init-failed", error=str(exc))
            self._ytmusic = None

    # ---- public API --------------------------------------------------------
    async def search(self, query: str, limit: int = 25) -> list[Track]:
        query = query.strip()
        if not query:
            return []

        cache_key = f"search:{normalize(query)}"
        if cached := await self.redis.get(cache_key):
            return [self._track_from_dict(d) for d in json.loads(cached)]

        # Fan out; a failing/slow source contributes nothing but never blocks.
        results = await asyncio.gather(
            self._guard(asyncio.wait_for(self._search_deezer(query), timeout=_PER_SOURCE_TIMEOUT)),
            self._guard(asyncio.wait_for(self._search_ytmusic(query), timeout=_PER_SOURCE_TIMEOUT)),
            self._guard(asyncio.wait_for(self._search_lastfm(query), timeout=_PER_SOURCE_TIMEOUT)),
            return_exceptions=False,
        )
        merged: list[Track] = [t for group in results for t in group]
        ranked = self._dedup_and_rank(merged)[:limit]

        await self.redis.set(
            cache_key,
            json.dumps([self._track_to_dict(t) for t in ranked]),
            ex=_CACHE_TTL,
        )
        return ranked

    async def get_track(self, ref: str) -> Track | None:
        """Resolve a single track by ref, primarily from the fresh-search cache;
        falls back to a direct Deezer lookup."""
        source, sid = Track.from_ref(ref)
        if source is Source.DEEZER:
            return await self._deezer_track(sid)
        # For other sources we rely on the cached search payload.
        if cached := await self.redis.get(f"track:{ref}"):
            return self._track_from_dict(json.loads(cached))
        return None

    async def cache_track(self, track: Track) -> None:
        await self.redis.set(
            f"track:{track.ref}", json.dumps(self._track_to_dict(track)), ex=86400
        )

    # ---- discovery ---------------------------------------------------------
    async def get_artist_top(self, artist_id: str, limit: int = 15) -> list[Track]:
        if not artist_id:
            return []
        data = await self._guard_json(
            f"{_DEEZER_API}/artist/{artist_id}/top", {"limit": limit}
        )
        return [self._deezer_to_track(i) for i in (data or {}).get("data", [])]

    async def get_album_tracks(self, album_id: str) -> list[Track]:
        if not album_id:
            return []
        data = await self._guard_json(f"{_DEEZER_API}/album/{album_id}", {})
        album_title = (data or {}).get("title", "")
        cover = (data or {}).get("cover_xl")
        out: list[Track] = []
        for i in (data or {}).get("tracks", {}).get("data", []):
            t = self._deezer_to_track(i)
            t.album = t.album or album_title
            t.cover_url = t.cover_url or cover
            out.append(t)
        return out

    async def get_similar(self, artist: str, title: str, limit: int = 8) -> list[Track]:
        """Last.fm track.getSimilar -> resolve each to a real Deezer track."""
        if not settings.lastfm_api_key:
            # Fall back to "more from this artist" via a plain search.
            return (await self.search(artist))[:limit]
        data = await self._guard_json(
            _LASTFM_API,
            {
                "method": "track.getSimilar",
                "artist": artist,
                "track": title,
                "api_key": settings.lastfm_api_key,
                "format": "json",
                "limit": limit,
            },
        )
        similar = (data or {}).get("similartracks", {}).get("track", []) or []
        out: list[Track] = []
        for item in similar[:limit]:
            name = item.get("name", "")
            art = (item.get("artist") or {}).get("name", "")
            hits = await self._guard(self._search_deezer(f"{art} {name}"))
            if hits:
                out.append(hits[0])
        return out

    async def _guard_json(self, url: str, params: dict) -> dict | None:
        try:
            async with self.session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=_PER_SOURCE_TIMEOUT)
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("discovery-failed", url=url, error=str(exc))
            return None

    # ---- per-source implementations ---------------------------------------
    async def _search_deezer(self, query: str) -> list[Track]:
        async with self.session.get(
            f"{_DEEZER_API}/search",
            params={"q": query, "limit": 25},
            timeout=aiohttp.ClientTimeout(total=_PER_SOURCE_TIMEOUT),
        ) as resp:
            data = await resp.json()
        return [self._deezer_to_track(item) for item in data.get("data", [])]

    async def _deezer_track(self, sid: str) -> Track | None:
        async with self.session.get(
            f"{_DEEZER_API}/track/{sid}",
            timeout=aiohttp.ClientTimeout(total=_PER_SOURCE_TIMEOUT),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
        if data.get("error"):
            return None
        return self._deezer_to_track(data)

    def _deezer_to_track(self, item: dict) -> Track:
        artist = item.get("artist", {}) or {}
        album = item.get("album", {}) or {}
        return Track(
            source=Source.DEEZER,
            source_id=str(item.get("id")),
            title=item.get("title", "").strip(),
            artist=artist.get("name", "").strip(),
            album=album.get("title", "").strip(),
            duration=int(item.get("duration", 0) or 0),
            cover_url=album.get("cover_xl") or album.get("cover_big"),
            preview_url=item.get("preview") or None,
            isrc=item.get("isrc", ""),
            artist_id=str(artist.get("id", "")),
            album_id=str(album.get("id", "")),
            popularity=int(item.get("rank", 0) or 0),
        )

    async def _search_ytmusic(self, query: str) -> list[Track]:
        if self._ytmusic is None:
            return []
        loop = asyncio.get_running_loop()
        try:
            raw = await asyncio.wait_for(
                loop.run_in_executor(
                    None, lambda: self._ytmusic.search(query, filter="songs", limit=15)
                ),
                timeout=_PER_SOURCE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            log.warning("ytmusic-search-timeout")
            return []
        except Exception as exc:
            log.warning("ytmusic-search-failed", error=str(exc))
            return []
        out: list[Track] = []
        for item in raw:
            artists = ", ".join(a["name"] for a in item.get("artists", []) if a.get("name"))
            thumbs = item.get("thumbnails") or []
            out.append(
                Track(
                    source=Source.YTMUSIC,
                    source_id=item.get("videoId", ""),
                    title=item.get("title", ""),
                    artist=artists,
                    album=(item.get("album") or {}).get("name", "") if item.get("album") else "",
                    duration=int(item.get("duration_seconds", 0) or 0),
                    cover_url=thumbs[-1]["url"] if thumbs else None,
                )
            )
        return [t for t in out if t.source_id and t.title]

    async def _search_lastfm(self, query: str) -> list[Track]:
        if not settings.lastfm_api_key:
            return []
        async with self.session.get(
            _LASTFM_API,
            params={
                "method": "track.search",
                "track": query,
                "api_key": settings.lastfm_api_key,
                "format": "json",
                "limit": 15,
            },
            timeout=aiohttp.ClientTimeout(total=_PER_SOURCE_TIMEOUT),
        ) as resp:
            data = await resp.json()
        matches = (
            data.get("results", {}).get("trackmatches", {}).get("track", []) or []
        )
        out = []
        for item in matches:
            out.append(
                Track(
                    source=Source.LASTFM,
                    source_id=item.get("mbid") or f"{item.get('artist')}-{item.get('name')}",
                    title=item.get("name", ""),
                    artist=item.get("artist", ""),
                    popularity=int(item.get("listeners", 0) or 0),
                )
            )
        return out

    # ---- dedup + ranking ---------------------------------------------------
    def _dedup_and_rank(self, tracks: list[Track]) -> list[Track]:
        """Collapse near-duplicate (artist, title) pairs, keeping the
        highest-priority source; then sort by priority, then popularity."""
        kept: list[Track] = []
        for track in tracks:
            match_idx = self._find_duplicate(track, kept)
            if match_idx is None:
                kept.append(track)
            elif track.source.priority < kept[match_idx].source.priority:
                # Prefer the better source but carry over a preview/cover if the
                # incumbent lacked one.
                track.cover_url = track.cover_url or kept[match_idx].cover_url
                track.preview_url = track.preview_url or kept[match_idx].preview_url
                kept[match_idx] = track

        kept.sort(key=lambda t: (t.source.priority, -t.popularity))
        return kept

    @staticmethod
    def _find_duplicate(track: Track, pool: list[Track]) -> int | None:
        a, t = track.norm_key
        for i, other in enumerate(pool):
            oa, ot = other.norm_key
            if (
                fuzz.token_sort_ratio(a, oa) >= _DEDUP_THRESHOLD
                and fuzz.token_sort_ratio(t, ot) >= _DEDUP_THRESHOLD
            ):
                return i
        return None

    # ---- helpers -----------------------------------------------------------
    @staticmethod
    async def _guard(coro) -> list[Track]:
        """Never let one source's failure abort the whole search."""
        try:
            return await coro
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("search-source-failed", error=str(exc))
            return []
        except Exception as exc:  # pragma: no cover
            log.error("search-source-error", error=str(exc))
            return []

    @staticmethod
    def _track_to_dict(t: Track) -> dict:
        d = asdict(t)
        d["source"] = t.source.value
        return d

    @staticmethod
    def _track_from_dict(d: dict) -> Track:
        d = dict(d)
        d["source"] = Source(d["source"])
        return Track(**d)
