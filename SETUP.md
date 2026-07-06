# Setup Guide

A metadata-driven Telegram music bot: multi-source search, preview delivery,
auto cover art, an FX/remix engine, lyrics, and 6-language UI.

> **Legality first.** This bot serves **metadata** and the **30-second previews**
> that Deezer/Spotify publish for third-party playback. It does **not** rip or
> redistribute full copyrighted tracks. Full-track delivery is gated behind a
> `LicensedAudioSource` (see [`bot/services/audio_source.py`](bot/services/audio_source.py))
> that you point at a catalog **you are licensed to serve** (your own uploads, a
> label deal, a paid distributor API, etc.). Leave it unset and the bot runs in
> preview-only mode with zero code changes.

---

## 1. Get your API keys

| Service | Needed? | Where | Notes |
|---|---|---|---|
| **Telegram Bot Token** | ✅ required | [@BotFather](https://t.me/BotFather) → `/newbot` | Also enable inline mode: `/setinline`. |
| **Deezer** | ✅ (keyless) | — | Public API, no key. Provides search + covers + previews. |
| **YouTube Music** | ✅ (keyless) | — | `ytmusicapi` needs no key for search. |
| **Genius** | optional | [genius.com/api-clients](https://genius.com/api-clients) | Client access token → lyrics. |
| **Last.fm** | optional | [last.fm/api/account/create](https://www.last.fm/api/account/create) | Enables "Similar Tracks" and metadata enrichment. |
| **Spotify** | optional | [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) | Extra metadata/previews (client credentials flow). |
| **Licensed source** | optional | your backend | Full-track delivery. See the contract in `audio_source.py`. |

Put them all in `.env` (copy from `.env.example`):

```bash
cp .env.example .env
# then edit .env — at minimum set BOT_TOKEN and BOT_USERNAME
```

---

## 2. Run with Docker (recommended)

Everything (bot, Postgres, Redis, Celery worker, Flower) comes up together:

```bash
docker compose up -d --build
docker compose logs -f bot
```

- Health check: <http://localhost:8080/health> → `{"status":"ok", ...}`
- Celery monitoring (Flower): <http://localhost:5555>
- Stop: `docker compose down` (add `-v` to wipe Postgres/Redis volumes)

The `bot` service waits for Postgres and Redis to be healthy before starting,
and tables are auto-created on first boot.

---

## 3. Run locally for development

You still need Postgres + Redis + ffmpeg available. Easiest is to run just the
infra in Docker and the bot on your host:

```bash
# 1) infra only
docker compose up -d postgres redis

# 2) system deps (Debian/Ubuntu example)
sudo apt install ffmpeg libsndfile1 fonts-dejavu-core

# 3) python env
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 4) point .env at localhost
#    POSTGRES_HOST=localhost
#    REDIS_HOST=localhost

# 5) run the bot
python -m bot.main

# 6) (optional) heavy-FX worker in another terminal
celery -A workers.fx_worker:celery_app worker --loglevel=info --concurrency=2
```

---

## 4. Redis + PostgreSQL configuration

Both are configured entirely from `.env`:

```ini
POSTGRES_HOST=postgres     # 'localhost' for host-run dev
POSTGRES_PORT=5432
POSTGRES_DB=musicbot
POSTGRES_USER=musicbot
POSTGRES_PASSWORD=change-me

REDIS_HOST=redis           # 'localhost' for host-run dev
REDIS_PORT=6379
REDIS_DB=0
```

- **Postgres** stores users, likes, `file_id` reuse cache, and artist
  subscriptions. Connection pool is 5–20 (`asyncpg`). Schema is created
  automatically; for production migrations, add Alembic.
- **Redis** backs: search cache (1h TTL), track/lyrics/cover caches, the
  paginated result sets, anti-flood counters, analytics, aiogram FSM storage,
  and the Celery broker/result backend.

---

## 5. What works out of the box vs. what you plug in

| Feature | Out of the box | Needs config |
|---|---|---|
| Search (Deezer + YT Music) | ✅ | — |
| 30s preview delivery + inline | ✅ | — |
| Auto cover art / glassmorphism | ✅ | logo/bg optional |
| FX/remix engine | ✅ | — |
| Similar tracks | partial | Last.fm key for best results |
| Lyrics + translation | — | Genius token |
| **Full-track / FLAC delivery** | ❌ | `LicensedAudioSource` |

---

## 6. Project layout

See the module tree under [`bot/`](bot/). Entry point is
[`bot/main.py`](bot/main.py); it builds the shared clients, wires the
middleware chain (DB → i18n → flood → analytics), includes the routers, starts
the health server, and long-polls with graceful shutdown.
