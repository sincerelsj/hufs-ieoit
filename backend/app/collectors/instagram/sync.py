"""Instagram 채널 동기화: Graph API 게시물 → 미디어 복사 → `upsert_post`.

보안: Graph API URL(토큰 포함)은 로그·출력에 남기지 않는다. 이 모듈은 아무것도 출력하지 않는다.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.archive.ingest import MediaIn, PostIn, upsert_post
from app.collectors.instagram.client import (
    InstagramAuthError,
    InstagramClient,
    InstagramError,
    InstagramRateLimitError,
)
from app.config import Settings
from app.models import Channel, Organization, Post, PostMedia
from app.security import TokenDecryptError, decrypt_token
from app.storage import MediaStorage, media_key

_DEFAULT_CONTENT_TYPE = {"jpg": "image/jpeg", "mp4": "video/mp4"}


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    media_failed: int = 0
    error: str | None = None  # "needs_reauth" | "rate_limited" | "failed" | None


def to_post_in(item: dict, media: tuple[MediaIn, ...]) -> PostIn:
    posted_at = datetime.strptime(item["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc)
    return PostIn(
        source="instagram_api",
        dedupe_key=f"ig:{item['id']}",
        posted_at=posted_at,
        media_type=item["media_type"],
        caption=item.get("caption"),
        permalink=item.get("permalink"),
        owner_username=item.get("username"),
        raw_payload=item,
        media=media,
    )


def _download(http: httpx.Client, storage: MediaStorage, url: str, key: str, ext: str) -> bool:
    """CDN 파일을 저장소에 복사한다. 실패(비 2xx, 전송 오류)하면 False. 예외 메시지에 URL을 싣지 않는다."""
    try:
        response = http.get(url)
    except httpx.HTTPError:
        return False
    if not response.is_success:
        return False
    content_type = response.headers.get("content-type") or _DEFAULT_CONTENT_TYPE[ext]
    storage.put(key, response.content, content_type)
    return True


def _build_media(
    position: int,
    entry: dict,
    current: PostMedia | None,
    slug: str,
    storage: MediaStorage,
    http: httpx.Client,
    result: SyncResult,
) -> MediaIn:
    """이미 저장된 키가 있는 파일은 다시 받지 않는다(--full 재시도는 키가 비어 있는 것만)."""
    media_type = entry["media_type"]
    ext = "mp4" if media_type == "VIDEO" else "jpg"
    storage_key = current.storage_key if current else None
    thumbnail_key = current.thumbnail_key if current else None

    media_url = entry.get("media_url")
    if media_url and storage_key is None:
        key = media_key(slug, entry["id"], ext)
        if _download(http, storage, media_url, key, ext):
            storage_key = key
        else:
            result.media_failed += 1

    thumbnail_url = entry.get("thumbnail_url")
    if media_type == "VIDEO" and thumbnail_url and thumbnail_key is None:
        key = media_key(slug, f"{entry['id']}_thumb", "jpg")
        if _download(http, storage, thumbnail_url, key, "jpg"):
            thumbnail_key = key
        else:
            result.media_failed += 1

    return MediaIn(
        position=position,
        media_type=media_type,
        storage_key=storage_key,
        thumbnail_key=thumbnail_key,
        source_url=media_url,
    )


def _media_entries(item: dict) -> list[dict]:
    if item["media_type"] == "CAROUSEL_ALBUM":
        return item.get("children", {}).get("data", [])
    return [item]


def sync_channel(
    session: Session,
    channel: Channel,
    client: InstagramClient,
    storage: MediaStorage,
    http: httpx.Client,
    settings: Settings,
    full: bool = False,
) -> SyncResult:
    result = SyncResult()
    if channel.access_token_enc is None:
        result.error = "needs_reauth"
        return result

    # commit하면 ORM 객체가 만료되므로 반복에 쓸 값은 미리 꺼내 둔다.
    organization_id = channel.organization_id
    channel_id = channel.id
    slug = session.scalar(select(Organization.slug).where(Organization.id == organization_id))

    try:
        token = decrypt_token(settings, channel.access_token_enc)
        for item in client.iter_media(token):
            existing = session.scalar(
                select(Post).where(
                    Post.organization_id == organization_id,
                    Post.dedupe_key == f"ig:{item['id']}",
                )
            )
            if existing is not None and not full:
                break  # 최신순이므로 이후는 모두 이미 저장된 게시물이다.

            current_media = {m.position: m for m in existing.media} if existing else {}
            media = tuple(
                _build_media(position, entry, current_media.get(position), slug, storage, http, result)
                for position, entry in enumerate(_media_entries(item))
            )
            _, created = upsert_post(session, organization_id, channel_id, to_post_in(item, media))
            session.commit()  # 게시물마다 확정해, 중간에 실패해도 앞부분은 남는다.
            if created:
                result.created += 1
            else:
                result.updated += 1
    except InstagramAuthError:
        channel.status = "needs_reauth"
        result.error = "needs_reauth"
        session.commit()
        return result
    except InstagramRateLimitError:
        result.error = "rate_limited"
        session.commit()
        return result
    except (InstagramError, TokenDecryptError):
        result.error = "failed"
        session.commit()
        return result

    channel.last_synced_at = datetime.now(timezone.utc)
    session.commit()
    return result


def sync_all(
    session: Session,
    client: InstagramClient,
    storage: MediaStorage,
    http: httpx.Client,
    settings: Settings,
    org_slug: str | None = None,
    full: bool = False,
) -> dict[str, SyncResult]:
    """활성 Instagram 채널을 모두 동기화한다. 한 채널의 실패가 다른 채널을 막지 않는다. 키: channel.handle."""
    stmt = select(Channel).where(Channel.platform == "instagram", Channel.status == "active")
    if org_slug is not None:
        stmt = stmt.join(Organization, Channel.organization_id == Organization.id).where(
            Organization.slug == org_slug
        )
    channels = session.scalars(stmt.order_by(Channel.id)).all()

    results: dict[str, SyncResult] = {}
    for channel in channels:
        handle = channel.handle
        try:
            results[handle] = sync_channel(session, channel, client, storage, http, settings, full=full)
        except Exception:  # noqa: BLE001 - 예상 밖 오류도 다른 채널 동기화를 막지 않는다.
            session.rollback()
            results[handle] = SyncResult(error="failed")
    return results
