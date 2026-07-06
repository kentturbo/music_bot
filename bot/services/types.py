"""Shared, source-agnostic data types."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum


class Source(str, Enum):
    """Where a result's *metadata* came from. Ordering doubles as search
    priority (lower = preferred). None of these imply the right to download
    a full track — only Deezer/Spotify previews are fetched by default."""

    DEEZER = "deezer"
    YTMUSIC = "ytmusic"
    SPOTIFY = "spotify"
    LASTFM = "lastfm"
    LICENSED = "licensed"  # operator-supplied full-track backend

    @property
    def badge(self) -> str:
        return {
            Source.DEEZER: "🔵",
            Source.YTMUSIC: "🔴",
            Source.SPOTIFY: "🟢",
            Source.LASTFM: "⚪",
            Source.LICENSED: "⭐",
        }[self]

    @property
    def priority(self) -> int:
        order = [
            Source.LICENSED,
            Source.DEEZER,
            Source.YTMUSIC,
            Source.SPOTIFY,
            Source.LASTFM,
        ]
        return order.index(self)


_NORMALIZE_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_FEAT_RE = re.compile(r"\s*[\(\[]?\bfeat\.?\b.*$", flags=re.IGNORECASE)


def normalize(text: str) -> str:
    """Fold a title/artist for fuzzy dedup: lowercase, strip feat./punctuation,
    collapse whitespace."""
    text = _FEAT_RE.sub("", text or "")
    text = _NORMALIZE_RE.sub(" ", text.lower())
    return " ".join(text.split())


@dataclass(slots=True)
class Track:
    source: Source
    source_id: str                 # id within that source
    title: str
    artist: str
    album: str = ""
    duration: int = 0              # seconds
    year: str = ""
    cover_url: str | None = None   # remote artwork, may be missing
    preview_url: str | None = None # 30s preview (Deezer/Spotify) — legal to fetch
    isrc: str = ""
    bitrate: int = 0               # kbps of the *deliverable* audio, 0 = unknown
    artist_id: str = ""
    album_id: str = ""
    popularity: int = 0            # source-specific rank, higher = more popular
    extra: dict = field(default_factory=dict)

    @property
    def ref(self) -> str:
        """Stable, source-qualified id used as cache/DB key and in callbacks."""
        return f"{self.source.value}__{self.source_id}"

    @property
    def norm_key(self) -> tuple[str, str]:
        return (normalize(self.artist), normalize(self.title))

    @property
    def duration_str(self) -> str:
        m, s = divmod(max(self.duration, 0), 60)
        return f"{m}:{s:02d}"

    @property
    def display(self) -> str:
        return f"{self.artist} — {self.title}"

    @classmethod
    def from_ref(cls, ref: str) -> tuple[Source, str]:
        src, _, sid = ref.partition("__")
        return Source(src), sid


def track_to_dict(t: Track) -> dict:
    d = asdict(t)
    d["source"] = t.source.value
    return d


def track_from_dict(d: dict) -> Track:
    d = dict(d)
    d["source"] = Source(d["source"])
    return Track(**d)
