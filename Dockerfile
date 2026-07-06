FROM python:3.12-slim AS base

# System deps: ffmpeg (pydub/librosa), libsndfile (soundfile), fonts (covers).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        fonts-dejavu-core \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run the bot. Compose overrides the command for the Celery worker.
CMD ["python", "-m", "bot.main"]
