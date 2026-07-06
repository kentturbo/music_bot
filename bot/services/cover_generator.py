"""Cover art: embed the real artwork when present, otherwise synthesize a
branded 1000x1000 cover with a gradient, glassmorphism panel, the track text
and a corner logo watermark.

All Pillow work is CPU-bound and runs in a thread executor so the event loop
never blocks.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
from pathlib import Path

import aiohttp
import structlog
from PIL import Image, ImageDraw, ImageFilter, ImageFont

log = structlog.get_logger(__name__)

SIZE = 1000
_ASSETS = Path(__file__).resolve().parent.parent.parent / "assets"
_LOGO_PATH = _ASSETS / "watermark_logo.png"
_FONT_DIR = Path("/usr/share/fonts")


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Best-effort TrueType lookup with a graceful fallback to the PIL bitmap
    font (so the bot still runs on a bare image without fonts installed)."""
    candidates = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "dejavu/DejaVuSans-Bold.ttf" if bold else "dejavu/DejaVuSans.ttf",
        "truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "truetype/dejavu/DejaVuSans.ttf",
    ]
    for rel in candidates:
        p = _FONT_DIR / rel
        if p.exists():
            return ImageFont.truetype(str(p), size)
    try:
        return ImageFont.truetype(candidates[0], size)
    except OSError:
        return ImageFont.load_default()


def _gradient_from_seed(seed: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Deterministic, pleasant two-color gradient derived from the track text
    so the same track always gets the same cover."""
    h = hashlib.sha256(seed.encode("utf-8")).digest()
    hue = h[0] / 255.0
    top = _hsv_to_rgb(hue, 0.55, 0.85)
    bottom = _hsv_to_rgb((hue + 0.08) % 1.0, 0.75, 0.35)
    return top, bottom


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    i = int(h * 6)
    f = h * 6 - i
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    r, g, b = [
        (v, t, p),
        (q, v, p),
        (p, v, t),
        (p, q, v),
        (t, p, v),
        (v, p, q),
    ][i % 6]
    return int(r * 255), int(g * 255), int(b * 255)


class CoverGenerator:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session
        self._logo = self._load_logo()

    @staticmethod
    def _load_logo() -> Image.Image | None:
        if _LOGO_PATH.exists():
            try:
                return Image.open(_LOGO_PATH).convert("RGBA")
            except OSError:
                return None
        return None

    async def get_cover(
        self, artist: str, title: str, cover_url: str | None
    ) -> bytes:
        """Return JPEG bytes: the resized real artwork if available, else a
        generated branded cover."""
        if cover_url:
            raw = await self._download(cover_url)
            if raw is not None:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None, self._finalize_real_cover, raw
                )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._generate, artist, title)

    async def _download(self, url: str) -> bytes | None:
        try:
            async with self.session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
        except (aiohttp.ClientError, TimeoutError):
            return None

    # ---- sync (executor) image ops ----------------------------------------
    def _finalize_real_cover(self, raw: bytes) -> bytes:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        if img.size != (SIZE, SIZE):
            img = _center_crop_square(img).resize((SIZE, SIZE), Image.LANCZOS)
        self._stamp_logo(img)
        return _to_jpeg(img)

    def _generate(self, artist: str, title: str) -> bytes:
        top, bottom = _gradient_from_seed(f"{artist}|{title}")
        img = _vertical_gradient(SIZE, SIZE, top, bottom)

        # Glassmorphism: a blurred, semi-transparent panel behind the text.
        panel_h = 360
        panel = Image.new("RGBA", (SIZE - 120, panel_h), (255, 255, 255, 38))
        blurred = img.filter(ImageFilter.GaussianBlur(28)).convert("RGBA")
        px, py = 60, (SIZE - panel_h) // 2
        region = blurred.crop((px, py, px + panel.width, py + panel.height))
        region = Image.alpha_composite(region, panel)
        _rounded_paste(img, region, (px, py), radius=40)

        draw = ImageDraw.Draw(img)
        title_font = _load_font(66, bold=True)
        artist_font = _load_font(44)

        title_lines = _wrap(draw, title.upper(), title_font, panel.width - 100)
        artist_line = _truncate(draw, artist, artist_font, panel.width - 100)

        y = py + 70
        for line in title_lines[:2]:
            _centered_text(draw, line, title_font, (255, 255, 255), y)
            y += 78
        y += 20
        _centered_text(draw, artist_line, artist_font, (235, 235, 235), y)

        self._stamp_logo(img)
        return _to_jpeg(img.convert("RGB"))

    def _stamp_logo(self, img: Image.Image) -> None:
        """Bottom-right logo watermark at ~15% opacity."""
        if self._logo is None:
            return
        logo = self._logo.copy()
        target_w = SIZE // 5
        ratio = target_w / logo.width
        logo = logo.resize((target_w, int(logo.height * ratio)), Image.LANCZOS)
        alpha = logo.split()[3].point(lambda a: int(a * 0.15))
        logo.putalpha(alpha)
        base = img.convert("RGBA")
        base.alpha_composite(
            logo, (SIZE - logo.width - 40, SIZE - logo.height - 40)
        )
        img.paste(base.convert("RGB"))


# ---- module-level image helpers -------------------------------------------
def _vertical_gradient(w: int, h: int, top, bottom) -> Image.Image:
    base = Image.new("RGB", (w, h), top)
    draw = ImageDraw.Draw(base)
    for y in range(h):
        f = y / h
        color = tuple(int(top[i] + (bottom[i] - top[i]) * f) for i in range(3))
        draw.line([(0, y), (w, y)], fill=color)
    return base


def _center_crop_square(img: Image.Image) -> Image.Image:
    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def _rounded_paste(base: Image.Image, region: Image.Image, pos, radius: int) -> None:
    mask = Image.new("L", region.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [(0, 0), region.size], radius=radius, fill=255
    )
    base.paste(region.convert("RGB"), pos, mask)


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [text]


def _truncate(draw, text: str, font, max_w: int) -> str:
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"


def _centered_text(draw, text: str, font, color, y: int) -> None:
    w = draw.textlength(text, font=font)
    draw.text(((SIZE - w) / 2, y), text, font=font, fill=color)


def _to_jpeg(img: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()
