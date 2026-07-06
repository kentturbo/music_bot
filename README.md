# Asynchronous Media Processing & Metadata Telegram Bot

A high-performance, asynchronous Telegram bot designed for music search, metadata delivery, dynamic cover art generation, and on-demand audio effects (remixes). Integrates multiple metadata sources (Deezer, YouTube Music, Spotify), supports lyrics retrieval, and provides a fully localized UI in 6 languages.

Built using **Python 3.12**, **aiogram v3**, **Celery**, **PostgreSQL**, and **Redis**.

---

## 🎨 Interface Preview (Screenshots)

> [!NOTE]
> Below are placeholders. Replace these with actual images when deployed.

| Interactive Flow | Preview |
|---|---|
| **Inline Music Search** (Multi-source results list) | ![Inline Search](screenshots/inline_search.png) |
| **Track Dashboard & Playback** (Interactive cover and audio details) | ![Track Interface](screenshots/track_play.png) |
| **Lyrics & Translations** (Synced scrolling text) | ![Lyrics Display](screenshots/lyrics.png) |
| **Audio FX & Remix Panel** (Reverb, speed, pitch adjustments) | ![FX Panel](screenshots/fx_panel.png) |

---

## 🚀 Key Features

*   **🔍 Multi-Source Search**: Concurrent querying of Deezer, YouTube Music, and Spotify APIs for track metadata, albums, and 30-second audio previews.
*   **🌐 6-Language UI Localisation**: Fully localized interface supporting **German, English, Spanish, Kazakh, Russian, and Ukrainian**. Controlled via custom aiogram middleware dynamically switching locales based on user settings.
*   **🎛️ Asynchronous Audio FX Engine**: Offloads heavy audio transcoding (speed adjustments, pitch shifting, reverb, and format conversion) using **Celery** workers and **FFmpeg**, preventing bot command bottlenecks.
*   **🎨 Glassmorphic Cover Art Overlay**: Dynamically overlays high-quality album art onto customized layout templates using **Pillow (PIL)** for a premium media presentation.
*   **⚡ Smart Caching & DB Storage**:
    *   **PostgreSQL** (`asyncpg` + SQLAlchemy) stores user preferences, track likes, and caches Telegram `file_id` parameters to bypass redundant audio uploads.
    *   **Redis** acts as the search results cache, Celery message broker, and user anti-flood tracking system.

---

## 🛠️ Technology Stack

*   **Language**: Python 3.12 (async/await paradigm)
*   **Telegram Framework**: aiogram v3 (routing, FSM, and custom middlewares)
*   **Database & Cache**: PostgreSQL, Redis, SQLAlchemy 2.0, asyncpg
*   **Task Queue**: Celery (asynchronous audio processing)
*   **Audio & Image Processing**: FFmpeg, Pillow (PIL), libsndfile
*   **Deployment**: Docker, Docker Compose, Nginx (healthcheck monitoring)

---

## 📁 Project Structure

```text
music_bot/
├── bot/                      # Core Telegram Bot Module
│   ├── handlers/             # Command handlers, inline search, and callback queries
│   ├── middlewares/          # i18n localization, DB session, anti-flood, analytics
│   ├── services/             # API connectors (Deezer, YouTube, Spotify, Genius)
│   └── models/               # SQLAlchemy DB models (User, Track, Like, Cache)
├── workers/                  # Celery worker module
│   └── fx_worker.py          # FFmpeg-based audio processing tasks
├── locales/                  # Translation catalogs (de, en, es, kk, ru, uk)
├── Dockerfile                # Multistage build for bot and workers
├── docker-compose.yml        # Orchestration (Bot, Worker, Postgres, Redis, Flower)
├── requirements.txt          # Python dependencies
├── SETUP.md                  # Comprehensive technical setup guide
└── README.md                 # Project summary and overview
```

---

## ⚙️ Quick Start

> **Legality Note:** Out of the box, the bot serves public metadata and official 30-second previews. Full-track delivery can be enabled by configuring a `LicensedAudioSource` pointing to a catalog you are legally authorized to distribute.

### 1. Configure Environment Variables
Copy the template file to `.env`:

```bash
cp .env.example .env
```

Open `.env` and set the following parameters at a minimum:
*   `BOT_TOKEN` — Your token from [@BotFather](https://t.me/BotFather)
*   `BOT_USERNAME` — Your bot's Telegram username
*   `GENIUS_TOKEN` — (Optional) Client access token from genius.com for lyrics

### 2. Launch with Docker (Recommended)
This command builds and spins up all containers (Bot, Postgres, Redis, Celery Worker, and Flower monitoring):

```bash
docker compose up -d --build
```

Monitor logs:
```bash
docker compose logs -f bot
```

*   **Health Status**: `http://localhost:8080/health`
*   **Celery Monitoring (Flower)**: `http://localhost:5555`

### 3. Local Development Run
If you prefer running the app on your host machine:

1.  Start only database and cache services:
    ```bash
    docker compose up -d postgres redis
    ```
2.  Install system dependencies (FFmpeg is required for audio manipulation):
    ```bash
    sudo apt install ffmpeg libsndfile1
    ```
3.  Set up a Python virtual environment and install requirements:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```
4.  Run the bot:
    ```bash
    python -m bot.main
    ```
5.  In a separate terminal, launch the Celery FX worker:
    ```bash
    celery -A workers.fx_worker:celery_app worker --loglevel=info --concurrency=2
    ```

---

## 📄 License
This project is licensed under the MIT License.
