"""Database access layer.

`Database` owns the async engine + session factory. `Repo` wraps a single
session and exposes the queries handlers actually need. Handlers get a fresh
`Repo` per update via a middleware (see main.py).
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.config import settings
from bot.db.models import (
    ArtistSubscription,
    Base,
    CachedFile,
    Like,
    User,
)


class Database:
    def __init__(self, dsn: str | None = None) -> None:
        self.engine = create_async_engine(
            dsn or settings.database_url,
            pool_size=5,
            max_overflow=15,  # -> up to 20 concurrent connections
            pool_pre_ping=True,
            echo=False,
        )
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    async def create_all(self) -> None:
        """Create tables if absent. For production use Alembic migrations."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def repo(self) -> AsyncIterator["Repo"]:
        async with self.session_factory() as session:
            yield Repo(session)

    async def dispose(self) -> None:
        await self.engine.dispose()


class Repo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- users -------------------------------------------------------------
    async def upsert_user(
        self, user_id: int, username: str | None, language: str | None
    ) -> User:
        """Create-or-touch a user. Only sets language on first insert so a
        user's explicit choice is never overwritten by their Telegram locale."""
        stmt = (
            pg_insert(User)
            .values(
                id=user_id,
                username=username,
                language=language or settings.default_language,
            )
            .on_conflict_do_update(
                index_elements=[User.id],
                set_={"username": username},
            )
            .returning(User)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.scalar_one()

    async def get_user(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def set_language(self, user_id: int, language: str) -> None:
        user = await self.session.get(User, user_id)
        if user:
            user.language = language
            await self.session.commit()

    async def get_language(self, user_id: int) -> str | None:
        user = await self.session.get(User, user_id)
        return user.language if user else None

    # ---- likes -------------------------------------------------------------
    async def toggle_like(
        self, user_id: int, track_ref: str, artist: str, title: str
    ) -> bool:
        """Return True if the track is now liked, False if it was un-liked."""
        existing = await self.session.scalar(
            select(Like).where(Like.user_id == user_id, Like.track_ref == track_ref)
        )
        if existing:
            await self.session.delete(existing)
            await self.session.commit()
            return False
        self.session.add(
            Like(user_id=user_id, track_ref=track_ref, artist=artist, title=title)
        )
        await self.session.commit()
        return True

    async def liked_count(self, user_id: int) -> int:
        return len(
            (
                await self.session.scalars(
                    select(Like.id).where(Like.user_id == user_id)
                )
            ).all()
        )

    # ---- cached telegram file_ids -----------------------------------------
    async def get_cached_file(self, track_ref: str, fx: str = "original") -> str | None:
        return await self.session.scalar(
            select(CachedFile.file_id).where(
                CachedFile.track_ref == track_ref, CachedFile.fx == fx
            )
        )

    async def store_cached_file(
        self, track_ref: str, file_id: str, fx: str = "original"
    ) -> None:
        stmt = (
            pg_insert(CachedFile)
            .values(track_ref=track_ref, fx=fx, file_id=file_id)
            .on_conflict_do_update(
                index_elements=[CachedFile.track_ref, CachedFile.fx],
                set_={"file_id": file_id},
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()

    # ---- artist subscriptions ---------------------------------------------
    async def subscribe_artist(
        self, user_id: int, artist_id: str, artist_name: str
    ) -> None:
        stmt = (
            pg_insert(ArtistSubscription)
            .values(user_id=user_id, artist_id=artist_id, artist_name=artist_name)
            .on_conflict_do_nothing(index_elements=["user_id", "artist_id"])
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def unsubscribe_artist(self, user_id: int, artist_id: str) -> None:
        await self.session.execute(
            delete(ArtistSubscription).where(
                ArtistSubscription.user_id == user_id,
                ArtistSubscription.artist_id == artist_id,
            )
        )
        await self.session.commit()
