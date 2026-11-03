from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UTCDateTime(TypeDecorator):
    """UTC로 저장하고 항상 timezone-aware(UTC)로 돌려준다 (SQLite는 tzinfo를 버린다)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timezone-aware datetime이 필요합니다 (naive datetime 거부)")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30))  # student_council | office | club
    department: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    terms: Mapped[list["Term"]] = relationship(back_populates="organization")
    channels: Mapped[list["Channel"]] = relationship(back_populates="organization")
    posts: Mapped[list["Post"]] = relationship(back_populates="organization")


class Term(Base):
    __tablename__ = "terms"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    ordinal: Mapped[int | None] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)  # NULL = 진행 중

    organization: Mapped[Organization] = relationship(back_populates="terms")
    posts: Mapped[list["Post"]] = relationship(back_populates="term")


class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = (UniqueConstraint("platform", "external_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    platform: Mapped[str] = mapped_column(String(30), default="instagram")
    handle: Mapped[str] = mapped_column(String(100))
    external_user_id: Mapped[str] = mapped_column(String(100))
    access_token_enc: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(30), default="active")
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # owner_token: 계정이 준 토큰(access_token_enc)으로 수집 | discovery: CollectorCredential로 handle을 조회
    collect_mode: Mapped[str] = mapped_column(String(30), default="owner_token")
    # discovery 수집이 한도 초과 등으로 중간에 멈췄을 때 이어서 받을 커서. 끝까지 받으면 비운다.
    sync_cursor: Mapped[str | None] = mapped_column(Text)

    organization: Mapped[Organization] = relationship(back_populates="channels")


class CollectorCredential(Base):
    """Business Discovery에 쓰는 우리 수집용 계정. 플랫폼마다 하나."""

    __tablename__ = "collector_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(30), unique=True, default="instagram")
    ig_user_id: Mapped[str] = mapped_column(String(100))
    username: Mapped[str] = mapped_column(String(100))
    access_token_enc: Mapped[str] = mapped_column(Text)  # 만료 없는 페이지 토큰
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (UniqueConstraint("organization_id", "dedupe_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(30))
    dedupe_key: Mapped[str] = mapped_column(String(200))
    posted_at: Mapped[datetime] = mapped_column(UTCDateTime)
    academic_year: Mapped[int] = mapped_column(Integer, index=True)
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id", ondelete="SET NULL"))
    term_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    caption: Mapped[str | None] = mapped_column(Text)
    permalink: Mapped[str | None] = mapped_column(String(500))
    media_type: Mapped[str] = mapped_column(String(30))
    owner_username: Mapped[str | None] = mapped_column(String(100))
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    organization: Mapped[Organization] = relationship(back_populates="posts")
    channel: Mapped[Channel | None] = relationship()
    term: Mapped[Term | None] = relationship(back_populates="posts")
    media: Mapped[list["PostMedia"]] = relationship(
        back_populates="post",
        order_by="PostMedia.position",
        cascade="all, delete-orphan",
    )


class PostMedia(Base):
    __tablename__ = "post_media"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    media_type: Mapped[str] = mapped_column(String(30))  # IMAGE | VIDEO
    storage_key: Mapped[str | None] = mapped_column(String(500))
    thumbnail_key: Mapped[str | None] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(Text)

    post: Mapped[Post] = relationship(back_populates="media")
