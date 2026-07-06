"""SQLAlchemy 2.x async ORM models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user id
    username: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(8), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    likes: Mapped[list["Like"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Like(Base):
    """A user's liked track. `track_ref` is a stable source-qualified id."""

    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("user_id", "track_ref", name="uq_like_user_track"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    track_ref: Mapped[str] = mapped_column(String(128))
    artist: Mapped[str] = mapped_column(String(256))
    title: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="likes")


class CachedFile(Base):
    """Telegram file_id reuse: once we upload an audio, resend by file_id.

    Keyed by (track_ref, fx) so an original and each remix cache separately.
    """

    __tablename__ = "cached_files"
    __table_args__ = (UniqueConstraint("track_ref", "fx", name="uq_cached_track_fx"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_ref: Mapped[str] = mapped_column(String(128), index=True)
    fx: Mapped[str] = mapped_column(String(32), default="original")
    file_id: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArtistSubscription(Base):
    """Notify a user when a subscribed artist releases something new."""

    __tablename__ = "artist_subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "artist_id", name="uq_sub_user_artist"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    artist_id: Mapped[str] = mapped_column(String(64))
    artist_name: Mapped[str] = mapped_column(String(256))
    last_known_release: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
