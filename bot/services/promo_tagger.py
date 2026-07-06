"""ID3 tag writer + bot self-promotion injection (mutagen).

Given raw MP3 bytes, a Track and a cover, returns MP3 bytes with:
  TIT2/TPE1/TALB   title / artist / album
  APIC             embedded cover (front)
  COMM / TPUB      promo comment + publisher
"""
from __future__ import annotations

import io

import structlog
from mutagen.id3 import (
    APIC,
    COMM,
    ID3,
    ID3NoHeaderError,
    TALB,
    TIT2,
    TPE1,
    TPUB,
    TYER,
)

from bot.config import settings
from bot.services.types import Track

log = structlog.get_logger(__name__)


def tag_audio(
    audio: bytes,
    track: Track,
    cover_jpeg: bytes | None,
    title_override: str | None = None,
) -> bytes:
    """Return a new MP3 byte string with tags + promo metadata written."""
    buf = io.BytesIO(audio)
    try:
        tags = ID3(buf)
    except ID3NoHeaderError:
        tags = ID3()

    tags.setall("TIT2", [TIT2(encoding=3, text=title_override or track.title)])
    tags.setall("TPE1", [TPE1(encoding=3, text=track.artist)])
    if track.album:
        tags.setall("TALB", [TALB(encoding=3, text=track.album)])
    if track.year:
        tags.setall("TYER", [TYER(encoding=3, text=track.year)])

    # --- self-promotion ---
    tags.setall(
        "COMM",
        [COMM(encoding=3, lang="eng", desc="", text=settings.promo_comment)],
    )
    tags.setall("TPUB", [TPUB(encoding=3, text=f"@{settings.bot_username}")])

    if cover_jpeg:
        tags.setall(
            "APIC",
            [
                APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,  # front cover
                    desc="Cover",
                    data=cover_jpeg,
                )
            ],
        )

    out = io.BytesIO(audio)
    tags.save(out)
    return out.getvalue()
