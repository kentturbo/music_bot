
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
import tempfile
from typing import Protocol

import aiohttp
import structlog

from bot.config import settings
from bot.services.types import Track, Source

log = structlog.get_logger(__name__)

_MAX_BYTES = 50 * 1024 * 1024  # Telegram bot API audio upload ceiling


@dataclass(slots=True)
class AudioResult:
    data: bytes | None    # None when url is set (stream directly to Telegram)
    mime: str
    bitrate: int          # kbps, 0 if unknown
    is_preview: bool      # True => 30s clip, not the full track
    ext: str = "mp3"
    url: str | None = None  # Direct URL for Telegram to fetch (skips server download)


class AudioSource(Protocol):
    async def fetch(self, track: Track) -> AudioResult | None: ...


class PreviewAudioSource:
    """Streams a track's published preview URL. Legal, keyless, always-on."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session

    async def fetch(self, track: Track) -> AudioResult | None:
        if not track.preview_url:
            return None
        data = await _stream(self.session, track.preview_url)
        if data is None:
            return None
        return AudioResult(data=data, mime="audio/mpeg", bitrate=128, is_preview=True)


class LicensedAudioSource:
    """Full-track retrieval from an operator-supplied, licensed backend.

    Contract — your backend should expose:
        GET {BASE_URL}/track?ref={track.ref}&isrc={isrc}
        Authorization: Bearer {LICENSED_SOURCE_API_KEY}
      -> 200 with the audio bytes and headers:
            Content-Type: audio/mpeg | audio/flac
            X-Bitrate: 320            (optional)
      -> 404 if the track isn't in your licensed catalog.

    If LICENSED_SOURCE_BASE_URL is unset this source is inert (returns None),
    so the bot falls back to previews with no code changes.
    """

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session
        self.base = settings.licensed_source_base_url.rstrip("/")
        self.key = settings.licensed_source_api_key.get_secret_value()

    @property
    def enabled(self) -> bool:
        return bool(self.base)

    async def fetch(self, track: Track) -> AudioResult | None:
        if not self.enabled:
            return None
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        try:
            async with self.session.get(
                f"{self.base}/track",
                params={"ref": track.ref, "isrc": track.isrc},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await _read_capped(resp)
                if data is None:
                    return None
                mime = resp.headers.get("Content-Type", "audio/mpeg")
                bitrate = int(resp.headers.get("X-Bitrate", "0") or 0)
        except (aiohttp.ClientError, TimeoutError) as exc:
            log.warning("licensed-fetch-failed", ref=track.ref, error=str(exc))
            return None
        ext = "flac" if "flac" in mime else "mp3"
        return AudioResult(
            data=data, mime=mime, bitrate=bitrate, is_preview=False, ext=ext
        )


class VkAudioSource:
    """Full-track retrieval from VKontakte using the vkpymusic library."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session
        self.token = settings.vk_token
        self.user_agent = settings.vk_user_agent
        self.service = None
        if self.enabled:
            # Check if VK API domain resolves to avoid long blocking hangs in environments where VK is blocked/restricted.
            import socket
            try:
                socket.gethostbyname("api.vk.com")
                from vkpymusic import Service
                self.service = Service(self.user_agent, self.token)
            except (socket.gaierror, Exception) as exc:
                log.warning("vk-api-unresolvable-disabling", error=str(exc))

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.user_agent and self.service)

    async def fetch(self, track: Track) -> AudioResult | None:
        if not self.enabled or not self.service:
            return None

        # Search VKontakte for the matching track
        query = f"{track.artist} - {track.title}"
        try:
            songs = await asyncio.wait_for(
                self.service.search_songs_by_text_async(query, count=5),
                timeout=4.0
            )
        except Exception as exc:
            log.warning("vk-search-failed", query=query, error=str(exc))
            return None

        if not songs:
            return None

        # Match: prefer duration-close results, fall back to top result.
        best_song = None
        for song in songs:
            if track.duration > 0 and abs(song.duration - track.duration) <= 20:
                best_song = song
                break
        if best_song is None:
            best_song = songs[0]

        url = best_song.url
        if not url:
            return None

        # For plain MP3 links, pass the URL directly to Telegram — no server download needed.
        if "index.m3u8" not in url:
            log.info("vk-direct-url", song=str(best_song))
            return AudioResult(
                data=None,
                mime="audio/mpeg",
                bitrate=320,
                is_preview=False,
                ext="mp3",
                url=url,
            )

        # HLS stream: must convert to MP3 locally via PyAV.
        try:
            from vkpymusic.utils import download_m3u8_as_mp3_pyav

            scratch_dir = os.path.join(os.getcwd(), "scratch")
            os.makedirs(scratch_dir, exist_ok=True)

            with tempfile.NamedTemporaryFile(dir=scratch_dir, suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                await asyncio.to_thread(download_m3u8_as_mp3_pyav, url, tmp_path)
                with open(tmp_path, "rb") as f:
                    data = f.read()
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        except Exception as exc:
            log.warning("vk-hls-convert-failed", song=str(best_song), error=str(exc))
            return None

        if len(data) > _MAX_BYTES:
            log.warning("vk-audio-too-large", size=len(data))
            return None

        return AudioResult(
            data=data,
            mime="audio/mpeg",
            bitrate=320,
            is_preview=False,
            ext="mp3",
        )


class YoutubeAudioSource:
    """Full-track retrieval from YouTube using yt-dlp."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session

    async def fetch(self, track: Track) -> AudioResult | None:
        import yt_dlp

        # If YTMUSIC, use the videoId directly, otherwise use search query
        if track.source == Source.YTMUSIC and track.source_id:
            url_or_search = f"https://www.youtube.com/watch?v={track.source_id}"
        else:
            url_or_search = f"ytsearch1:{track.artist} - {track.title}"

        scratch_dir = os.path.join(os.getcwd(), "scratch")
        os.makedirs(scratch_dir, exist_ok=True)

        with tempfile.NamedTemporaryFile(dir=scratch_dir, suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': tmp_path.removesuffix('.mp3'),
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'ignoreerrors': True,
        }

        try:
            loop = asyncio.get_running_loop()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await loop.run_in_executor(
                    None, lambda: ydl.extract_info(url_or_search, download=True)
                )
                if not info:
                    return None

            if os.path.exists(tmp_path):
                with open(tmp_path, "rb") as f:
                    data = f.read()
                return AudioResult(
                    data=data,
                    mime="audio/mpeg",
                    bitrate=192,
                    is_preview=False,
                    ext="mp3",
                )
            return None
        except Exception as exc:
            log.warning("youtube-download-failed", track=track.ref, error=str(exc))
            return None
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            base_path = tmp_path.removesuffix('.mp3')
            for ext in ['.webm', '.m4a', '.mp4', '.opus', '.ogg']:
                p = base_path + ext
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass


class AudioResolver:
    """Tries the licensed backend first, then VKontakte, then YouTube, then falls back to a legal preview."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.licensed = LicensedAudioSource(session)
        self.vk = VkAudioSource(session)
        self.youtube = YoutubeAudioSource(session)
        self.preview = PreviewAudioSource(session)

    async def resolve(self, track: Track) -> AudioResult | None:
        if self.licensed.enabled:
            if result := await self.licensed.fetch(track):
                return result
        if self.vk.enabled:
            # VK is configured: use it and don't fall back to a 30s preview.
            if result := await self.vk.fetch(track):
                return result
        # Fallback to YouTube for full-track delivery
        if result := await self.youtube.fetch(track):
            return result
        # No full-track source configured: fall back to legal 30s preview.
        return await self.preview.fetch(track)


# ---- streaming helpers -----------------------------------------------------
async def _stream(session: aiohttp.ClientSession, url: str) -> bytes | None:
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            if resp.status != 200:
                return None
            return await _read_capped(resp)
    except (aiohttp.ClientError, TimeoutError) as exc:
        log.warning("stream-failed", url=url, error=str(exc))
        return None


async def _read_capped(resp: aiohttp.ClientResponse) -> bytes | None:
    """Read in chunks, aborting if the payload exceeds Telegram's limit."""
    buf = bytearray()
    async for chunk in resp.content.iter_chunked(64 * 1024):
        buf.extend(chunk)
        if len(buf) > _MAX_BYTES:
            log.warning("audio-too-large")
            return None
    return bytes(buf)
