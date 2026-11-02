from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.archive.academic_year import academic_year
from app.archive.terms import find_term
from app.models import Post, PostMedia


@dataclass(frozen=True)
class MediaIn:
    position: int
    media_type: str  # "IMAGE" | "VIDEO"
    storage_key: str | None
    thumbnail_key: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class PostIn:
    source: str  # "instagram_api" | "instagram_export" | "manual"
    dedupe_key: str
    posted_at: datetime  # aware
    media_type: str
    caption: str | None = None
    permalink: str | None = None
    owner_username: str | None = None
    raw_payload: dict | None = None
    media: tuple[MediaIn, ...] = ()


def _new_media(media_in: MediaIn) -> PostMedia:
    return PostMedia(
        position=media_in.position,
        media_type=media_in.media_type,
        storage_key=media_in.storage_key,
        thumbnail_key=media_in.thumbnail_key,
        source_url=media_in.source_url,
    )


def _merge_media(post: Post, incoming: tuple[MediaIn, ...]) -> None:
    """위치(position)로 짝지어, 비어 있는 키만 채우고 없는 위치는 추가한다. 기존 키 덮어쓰기·삭제는 하지 않는다."""
    existing = {m.position: m for m in post.media}
    for media_in in incoming:
        current = existing.get(media_in.position)
        if current is None:
            created = _new_media(media_in)
            post.media.append(created)
            existing[media_in.position] = created
            continue
        if current.storage_key is None and media_in.storage_key is not None:
            current.storage_key = media_in.storage_key
        if current.thumbnail_key is None and media_in.thumbnail_key is not None:
            current.thumbnail_key = media_in.thumbnail_key


def upsert_post(
    session: Session, organization_id: int, channel_id: int | None, post_in: PostIn
) -> tuple[Post, bool]:
    """(post, created). 기존이면 caption·permalink·raw_payload 갱신, storage_key가 None인 미디어만 새 키로 채움.

    flush만 하며 commit은 호출자 몫이다. 기존 게시물의 임기·잠금·게시 시각·학년도는 건드리지 않는다.
    """
    post = session.scalar(
        select(Post).where(
            Post.organization_id == organization_id, Post.dedupe_key == post_in.dedupe_key
        )
    )

    if post is None:
        term = find_term(session, organization_id, post_in.posted_at)
        post = Post(
            organization_id=organization_id,
            channel_id=channel_id,
            source=post_in.source,
            dedupe_key=post_in.dedupe_key,
            posted_at=post_in.posted_at,
            academic_year=academic_year(post_in.posted_at),
            term_id=term.id if term else None,
            term_locked=False,
            caption=post_in.caption,
            permalink=post_in.permalink,
            media_type=post_in.media_type,
            owner_username=post_in.owner_username,
            raw_payload=post_in.raw_payload,
            media=[_new_media(m) for m in post_in.media],
        )
        session.add(post)
        session.flush()
        return post, True

    post.caption = post_in.caption
    post.permalink = post_in.permalink
    post.raw_payload = post_in.raw_payload
    if post_in.owner_username is not None:
        post.owner_username = post_in.owner_username
    if post_in.media_type:
        post.media_type = post_in.media_type
    if post.channel_id is None:
        post.channel_id = channel_id
    _merge_media(post, post_in.media)
    session.flush()
    return post, False
