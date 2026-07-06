"""Tiny aiohttp health-check server for Docker/K8s liveness probes."""
from __future__ import annotations

from aiohttp import web
from redis.asyncio import Redis
from sqlalchemy import text

from bot.db.repository import Database


def build_health_app(redis: Redis, db: Database) -> web.Application:
    app = web.Application()

    async def health(_: web.Request) -> web.Response:
        checks = {"redis": False, "postgres": False}
        try:
            checks["redis"] = bool(await redis.ping())
        except Exception:  # noqa: BLE001
            pass
        try:
            async with db.session_factory() as s:
                await s.execute(text("SELECT 1"))
            checks["postgres"] = True
        except Exception:  # noqa: BLE001
            pass
        ok = all(checks.values())
        return web.json_response(
            {"status": "ok" if ok else "degraded", **checks},
            status=200 if ok else 503,
        )

    app.router.add_get("/health", health)
    return app


async def start_health_server(app: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    return runner
