"""Audio FX / remix engine.

Each effect is a pure function `AudioSegment -> AudioSegment`. They are
CPU-bound (numpy / librosa / pedalboard), so `apply_fx` dispatches them through
a thread executor; the heaviest ones (karaoke, 8d) are additionally routed to
Celery by the remix router.

Design: keep the DSP in small, testable functions and let the async layer
(apply_fx) own the executor hop and the AudioSegment<->ndarray marshalling.
"""
from __future__ import annotations

import asyncio
import io
from collections.abc import Callable

import numpy as np
from pydub import AudioSegment

try:
    from pedalboard import Pedalboard, Reverb  # Spotify's DSP lib

    _HAS_PEDALBOARD = True
except Exception:  # pragma: no cover - optional
    _HAS_PEDALBOARD = False


# ---- (de)serialization helpers --------------------------------------------
def _to_float_array(seg: AudioSegment) -> tuple[np.ndarray, int]:
    """Return float32 samples shaped (channels, n) in [-1, 1] and the rate."""
    samples = np.array(seg.get_array_of_samples())
    if seg.channels == 2:
        samples = samples.reshape((-1, 2)).T
    else:
        samples = samples.reshape((1, -1))
    max_val = float(1 << (8 * seg.sample_width - 1))
    return samples.astype(np.float32) / max_val, seg.frame_rate


def _from_float_array(arr: np.ndarray, rate: int, sample_width: int = 2) -> AudioSegment:
    arr = np.clip(arr, -1.0, 1.0)
    max_val = float(1 << (8 * sample_width - 1))
    ints = (arr * (max_val - 1)).astype(np.int16)
    interleaved = ints.T.flatten() if ints.ndim == 2 else ints
    return AudioSegment(
        interleaved.tobytes(),
        frame_rate=rate,
        sample_width=sample_width,
        channels=arr.shape[0] if arr.ndim == 2 else 1,
    )


def _resample_speed(seg: AudioSegment, factor: float) -> AudioSegment:
    """Classic tape-style speed change: retag the frame rate (shifts speed AND
    pitch together), then resample back to a standard rate. Used by nightcore /
    daycore / speed presets."""
    shifted = seg._spawn(seg.raw_data, overrides={"frame_rate": int(seg.frame_rate * factor)})
    return shifted.set_frame_rate(44100)


# ---- effects (sync, pure) --------------------------------------------------
def nightcore(audio: AudioSegment) -> AudioSegment:
    """+25% speed & pitch — bright, sped-up."""
    return _resample_speed(audio, 1.25)


def daycore(audio: AudioSegment) -> AudioSegment:
    """-20% speed & pitch — dreamy, slowed."""
    return _resample_speed(audio, 0.80)


def slowed_reverb(audio: AudioSegment) -> AudioSegment:
    """0.85x slow + hall reverb."""
    slow = _resample_speed(audio, 0.85)
    if not _HAS_PEDALBOARD:
        return slow  # graceful: still slowed even without pedalboard
    arr, rate = _to_float_array(slow)
    board = Pedalboard([Reverb(room_size=0.75, wet_level=0.35, dry_level=0.7)])
    processed = board(arr, rate)
    return _from_float_array(processed, rate)


def bass_boost(audio: AudioSegment) -> AudioSegment:
    """+8 dB low-shelf around 80 Hz."""
    from pydub.scipy_effects import low_pass_filter

    low = low_pass_filter(audio, 150).apply_gain(8)
    return audio.overlay(low)


def audio_8d(audio: AudioSegment) -> AudioSegment:
    """Simulated 8D: a slow left<->right pan oscillation."""
    stereo = audio.set_channels(2)
    arr, rate = _to_float_array(stereo)
    n = arr.shape[1]
    t = np.arange(n) / rate
    pan = np.sin(2 * np.pi * 0.15 * t)  # ~6.6s per full sweep
    left_gain = np.sqrt(np.clip(0.5 * (1 - pan), 0, 1))
    right_gain = np.sqrt(np.clip(0.5 * (1 + pan), 0, 1))
    arr[0] *= left_gain
    arr[1] *= right_gain
    return _from_float_array(arr, rate)


def lofi(audio: AudioSegment) -> AudioSegment:
    """Warm lo-fi: 3 kHz lowpass + gentle slow + subtle noise bed."""
    from pydub.scipy_effects import low_pass_filter

    warm = low_pass_filter(_resample_speed(audio, 0.97), 3000)
    arr, rate = _to_float_array(warm)
    noise = (np.random.default_rng(0).standard_normal(arr.shape) * 0.004).astype(np.float32)
    return _from_float_array(arr + noise, rate)


def karaoke(audio: AudioSegment) -> AudioSegment:
    """Vocal removal via center-channel cancellation (L - R). Works when the
    lead vocal is panned dead-center, which is the common case."""
    stereo = audio.set_channels(2)
    arr, rate = _to_float_array(stereo)
    side = (arr[0] - arr[1]) * 0.5  # the non-centered content
    mono = np.stack([side, side])
    return _from_float_array(mono, rate)


def vocals_only(audio: AudioSegment) -> AudioSegment:
    """Rough acapella: keep the center channel (L + R) and duck the sides."""
    stereo = audio.set_channels(2)
    arr, rate = _to_float_array(stereo)
    mid = (arr[0] + arr[1]) * 0.5
    side = (arr[0] - arr[1]) * 0.5
    vocal = mid - 0.7 * np.abs(side)  # suppress hard-panned instruments
    mono = np.stack([vocal, vocal])
    return _from_float_array(mono, rate)


def speed(audio: AudioSegment, factor: float) -> AudioSegment:
    return _resample_speed(audio, factor)


# ---- registry + async dispatch --------------------------------------------
FX_REGISTRY: dict[str, Callable[[AudioSegment], AudioSegment]] = {
    "nightcore": nightcore,
    "daycore": daycore,
    "slowed_reverb": slowed_reverb,
    "bass_boost": bass_boost,
    "8d": audio_8d,
    "lofi": lofi,
    "karaoke": karaoke,
    "vocals_only": vocals_only,
    "speed_075": lambda a: speed(a, 0.75),
    "speed_125": lambda a: speed(a, 1.25),
    "speed_150": lambda a: speed(a, 1.50),
}

# Human-readable title prefixes for the remixed track name.
FX_LABELS: dict[str, str] = {
    "nightcore": "Nightcore",
    "daycore": "Daycore",
    "slowed_reverb": "Slowed + Reverb",
    "bass_boost": "Bass Boosted",
    "8d": "8D Audio",
    "lofi": "Lo-Fi",
    "karaoke": "Karaoke",
    "vocals_only": "Vocals Only",
    "speed_075": "0.75x",
    "speed_125": "1.25x",
    "speed_150": "1.5x",
}

# Effects heavy enough to prefer offloading to Celery.
HEAVY_FX = {"karaoke", "vocals_only", "8d", "slowed_reverb"}


def apply_fx_sync(raw: bytes, fx: str, src_format: str = "mp3") -> bytes:
    """Decode -> apply -> re-encode to MP3. Pure/sync so Celery can call it too."""
    fn = FX_REGISTRY.get(fx)
    if fn is None:
        raise ValueError(f"unknown fx: {fx}")
    seg = AudioSegment.from_file(io.BytesIO(raw), format=src_format)
    out = fn(seg)
    buf = io.BytesIO()
    out.export(buf, format="mp3", bitrate="320k")
    return buf.getvalue()


async def apply_fx(raw: bytes, fx: str, src_format: str = "mp3") -> bytes:
    """Async wrapper: run the (blocking) DSP in the default thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, apply_fx_sync, raw, fx, src_format)
