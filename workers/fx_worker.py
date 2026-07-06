"""Celery worker for heavy audio FX (karaoke, 8D, slowed+reverb, vocals-only).

The bot can offload CPU-bound remixes here to keep the event loop responsive
under load. Tasks take/return raw audio bytes via the Redis result backend.

Run with:
    celery -A workers.fx_worker:celery_app worker --loglevel=info --concurrency=2
"""
from __future__ import annotations

from celery import Celery

from bot.config import settings
from bot.services.audio_fx import apply_fx_sync

celery_app = Celery(
    "music_bot",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="pickle",       # audio payloads are binary
    result_serializer="pickle",
    accept_content=["pickle"],
    task_time_limit=120,
    worker_prefetch_multiplier=1,   # heavy tasks: one at a time per process
)


@celery_app.task(name="fx.apply", bind=True, max_retries=1)
def apply_fx_task(self, raw: bytes, fx: str, src_format: str = "mp3") -> bytes:
    """Decode -> apply FX -> re-encode to 320k MP3. Pure/CPU-bound."""
    try:
        return apply_fx_sync(raw, fx, src_format)
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=2)
