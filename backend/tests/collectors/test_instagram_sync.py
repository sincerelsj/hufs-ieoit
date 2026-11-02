import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select

from app.collectors.instagram.client import InstagramClient
from app.archive.ingest import upsert_post
from app.collectors.instagram.sync import SyncResult, sync_all, sync_channel, to_post_in
from app.models import Channel, Organization, Post
from app.security import encrypt_token
from app.storage import LocalStorage

SAMPLES = Path(__file__).resolve().parents[3] / "data" / "samples" / "instagram"
BASE = "https://graph.instagram.com/v26.0"
CDN = "https://cdn.example.test/media"
IMAGE_BYTES = b"dummy-image-bytes"


def load_sample(name: str) -> dict:
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


@pytest.fixture
def page1() -> dict:
    return load_sample("media_page1.json")


@pytest.fixture
def page2() -> dict:
    return load_sample("media_page2.json")


@pytest.fixture
def http():
    with httpx.Client() as c:
        yield c


@pytest.fixture
def ig(http, settings) -> InstagramClient:
    return InstagramClient(
        http,
        settings.instagram_app_id,
        settings.instagram_app_secret,
        settings.instagram_api_version,
        sleep=lambda s: None,
    )


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(tmp_path / "store")


def make_channel(session, settings, slug="test-org", handle="dummy_account", ext_id="1") -> Channel:
    org = session.scalar(select(Organization).where(Organization.slug == slug))
    if org is None:
        org = Organization(slug=slug, name="테스트 조직", kind="student_council", department="테스트학과")
        session.add(org)
        session.flush()
    channel = Channel(
        organization_id=org.id,
        platform="instagram",
        handle=handle,
        external_user_id=ext_id,
        access_token_enc=encrypt_token(settings, "T"),
        status="active",
    )
    session.add(channel)
    session.commit()
    return channel


def mock_graph(page1: dict, page2: dict):
    first = respx.get(f"{BASE}/me/media").mock(return_value=httpx.Response(200, json=page1))
    second = respx.get(page1["paging"]["next"]).mock(return_value=httpx.Response(200, json=page2))
    return first, second


def mock_cdn(fail: set[str] | None = None) -> None:
    """CDN의 모든 미디어 URL을 200으로 응답한다. fail에 든 URL은 403."""
    for url in fail or set():
        respx.get(url).mock(return_value=httpx.Response(403))
    respx.get(url__startswith=CDN).mock(
        return_value=httpx.Response(200, content=IMAGE_BYTES, headers={"content-type": "image/jpeg"})
    )


def test_to_post_in_parses_timestamp():
    item = {
        "id": "123",
        "media_type": "IMAGE",
        "permalink": "https://www.instagram.com/p/DUMMY/",
        "timestamp": "2026-11-01T08:14:43+0000",
        "username": "dummy_account",
    }

    post_in = to_post_in(item, ())

    assert post_in.posted_at == datetime(2026, 11, 1, 8, 14, 43, tzinfo=timezone.utc)
    assert post_in.posted_at.utcoffset().total_seconds() == 0
    assert post_in.dedupe_key == "ig:123"
    assert post_in.source == "instagram_api"
    assert post_in.caption is None  # caption 키가 없는 게시물
    assert post_in.owner_username == "dummy_account"
    assert post_in.raw_payload == item


def test_to_post_in_converts_offset_to_utc():
    item = {"id": "1", "media_type": "IMAGE", "timestamp": "2026-11-01T17:14:43+0900"}

    post_in = to_post_in(item, ())

    assert post_in.posted_at == datetime(2026, 11, 1, 8, 14, 43, tzinfo=timezone.utc)
    assert post_in.posted_at.utcoffset().total_seconds() == 0


@respx.mock
def test_full_sync_creates_posts_and_media(session, settings, ig, storage, http, page1, page2):
    channel = make_channel(session, settings)
    mock_graph(page1, page2)
    mock_cdn()

    result = sync_channel(session, channel, ig, storage, http, settings, full=True)

    assert result == SyncResult(created=5, updated=0, media_failed=0, error=None)
    assert channel.last_synced_at is not None
    carousel = session.scalar(select(Post).where(Post.dedupe_key == "ig:17900000000000002"))
    assert [m.position for m in carousel.media] == [0, 1, 2]
    assert [m.media_type for m in carousel.media] == ["IMAGE", "VIDEO", "IMAGE"]
    assert carousel.media[0].storage_key == "instagram/test-org/17900000000000021.jpg"
    assert carousel.media[1].storage_key == "instagram/test-org/17900000000000022.mp4"
    assert carousel.media[1].thumbnail_key == "instagram/test-org/17900000000000022_thumb.jpg"
    assert carousel.media[1].source_url == f"{CDN}/17900000000000022.mp4"
    for m in carousel.media:
        assert storage.open(m.storage_key) == IMAGE_BYTES
    assert storage.open(carousel.media[1].thumbnail_key) == IMAGE_BYTES
    assert carousel.posted_at == datetime(2026, 10, 28, 3, 20, 10, tzinfo=timezone.utc)


@respx.mock
def test_incremental_stops_at_known(session, settings, ig, storage, http, page1, page2):
    channel = make_channel(session, settings)
    _, second = mock_graph(page1, page2)
    mock_cdn()
    sync_channel(session, channel, ig, storage, http, settings, full=True)
    assert second.call_count == 1
    respx.reset()
    first, second = mock_graph(page1, page2)
    cdn = respx.get(url__startswith=CDN).mock(return_value=httpx.Response(200, content=b"x"))

    result = sync_channel(session, channel, ig, storage, http, settings)

    assert result.created == 0
    assert result.error is None
    assert first.call_count == 1
    assert second.call_count == 0
    assert cdn.call_count == 0


def add_known_post(session, item: dict) -> None:
    """이전 실행이 이미 저장한 게시물을 만든다(미디어 없음)."""
    upsert_post(session, 1, None, to_post_in(item, ()))
    session.commit()


@respx.mock
def test_incremental_without_last_synced_walks_everything(
    session, settings, ig, storage, http, page1, page2
):
    # 첫 실행이 1페이지 뒤에 중단됐다고 가정: 최신 게시물만 있고 last_synced_at은 None.
    channel = make_channel(session, settings)
    assert channel.last_synced_at is None
    add_known_post(session, page1["data"][0])
    _, second = mock_graph(page1, page2)
    mock_cdn()

    result = sync_channel(session, channel, ig, storage, http, settings)

    assert second.call_count == 1
    assert result.created == 4
    assert result.updated == 1  # 이미 있던 게시물은 건너뛰지 않고 보완만 한다
    assert result.error is None
    assert len(session.scalars(select(Post)).all()) == 5
    assert channel.last_synced_at is not None


@respx.mock
def test_incremental_passes_known_posts_newer_than_last_sync(
    session, settings, ig, storage, http, page1, page2
):
    channel = make_channel(session, settings)
    channel.last_synced_at = datetime(2026, 10, 25, tzinfo=timezone.utc)
    session.commit()
    # 001(11/1): 중단된 실행이 남김(last_synced_at보다 새로움) / 003(10/20): 완료된 동기화가 저장
    add_known_post(session, page1["data"][0])
    add_known_post(session, page1["data"][2])
    _, second = mock_graph(page1, page2)
    mock_cdn()

    result = sync_channel(session, channel, ig, storage, http, settings)

    assert result.created == 1  # 002(10/28)는 새 게시물
    assert result.updated == 1  # 001은 지나치되 003에서 멈춘다
    assert second.call_count == 0
    assert session.scalar(select(Post).where(Post.dedupe_key == "ig:17900000000000002")) is not None


@respx.mock
def test_incremental_picks_up_only_new_posts(session, settings, ig, storage, http, page1, page2):
    channel = make_channel(session, settings)
    mock_graph(page1, page2)
    mock_cdn()
    sync_channel(session, channel, ig, storage, http, settings, full=True)
    new_item = {
        "id": "17900000000000099",
        "media_type": "IMAGE",
        "media_url": f"{CDN}/17900000000000099.jpg",
        "permalink": "https://www.instagram.com/p/DUMMY0099/",
        "timestamp": "2026-11-02T00:00:00+0000",
        "username": "dummy_account",
    }
    page1["data"].insert(0, new_item)
    respx.reset()
    _, second = mock_graph(page1, page2)
    mock_cdn()

    result = sync_channel(session, channel, ig, storage, http, settings)

    assert result.created == 1
    assert second.call_count == 0


@respx.mock
def test_full_sync_updates_existing_and_retries_failed_media(
    session, settings, ig, storage, http, page1, page2
):
    channel = make_channel(session, settings)
    failing = f"{CDN}/17900000000000001.jpg"
    mock_graph(page1, page2)
    mock_cdn(fail={failing})
    first_run = sync_channel(session, channel, ig, storage, http, settings, full=True)
    assert first_run.media_failed == 1
    respx.reset()
    mock_graph(page1, page2)
    only_failed = respx.get(failing).mock(
        return_value=httpx.Response(200, content=b"retry", headers={"content-type": "image/jpeg"})
    )
    others = respx.get(url__startswith=CDN).mock(return_value=httpx.Response(200, content=b"x"))

    result = sync_channel(session, channel, ig, storage, http, settings, full=True)

    assert result == SyncResult(created=0, updated=5, media_failed=0, error=None)
    assert only_failed.call_count == 1  # 실패했던 미디어만 다시 받는다
    assert others.call_count == 0
    post = session.scalar(select(Post).where(Post.dedupe_key == "ig:17900000000000001"))
    assert storage.open(post.media[0].storage_key) == b"retry"


@respx.mock
def test_media_download_failure_keeps_post(session, settings, ig, storage, http, page1):
    channel = make_channel(session, settings)
    page1["data"] = page1["data"][:1]
    page1.pop("paging")
    respx.get(f"{BASE}/me/media").mock(return_value=httpx.Response(200, json=page1))
    respx.get(f"{CDN}/17900000000000001.jpg").mock(return_value=httpx.Response(403))

    result = sync_channel(session, channel, ig, storage, http, settings, full=True)

    assert result.created == 1
    assert result.media_failed == 1
    assert result.error is None
    post = session.scalar(select(Post).where(Post.dedupe_key == "ig:17900000000000001"))
    assert post is not None
    assert post.media[0].storage_key is None
    assert post.media[0].source_url == f"{CDN}/17900000000000001.jpg"


@respx.mock
def test_media_download_follows_cdn_redirect(session, settings, ig, storage, http, page1):
    channel = make_channel(session, settings)
    page1["data"] = page1["data"][:1]
    page1.pop("paging")
    respx.get(f"{BASE}/me/media").mock(return_value=httpx.Response(200, json=page1))
    respx.get(f"{CDN}/17900000000000001.jpg").mock(
        return_value=httpx.Response(302, headers={"location": "https://cdn2.example.test/moved.jpg"})
    )
    respx.get("https://cdn2.example.test/moved.jpg").mock(
        return_value=httpx.Response(200, content=b"redirected", headers={"content-type": "image/jpeg"})
    )

    result = sync_channel(session, channel, ig, storage, http, settings, full=True)

    assert result.created == 1
    assert result.media_failed == 0
    post = session.scalar(select(Post).where(Post.dedupe_key == "ig:17900000000000001"))
    assert storage.open(post.media[0].storage_key) == b"redirected"


@respx.mock
def test_media_download_transport_error_keeps_post(session, settings, ig, storage, http, page1):
    channel = make_channel(session, settings)
    page1["data"] = page1["data"][:1]
    page1.pop("paging")
    respx.get(f"{BASE}/me/media").mock(return_value=httpx.Response(200, json=page1))
    respx.get(f"{CDN}/17900000000000001.jpg").mock(side_effect=httpx.ConnectError("boom"))

    result = sync_channel(session, channel, ig, storage, http, settings, full=True)

    assert result.created == 1
    assert result.media_failed == 1


@respx.mock
def test_thumbnail_download_failure_counts_as_failed(session, settings, ig, storage, http, page2):
    channel = make_channel(session, settings)
    page2.pop("paging")
    respx.get(f"{BASE}/me/media").mock(return_value=httpx.Response(200, json=page2))
    mock_cdn(fail={f"{CDN}/17900000000000004_thumb.jpg"})

    result = sync_channel(session, channel, ig, storage, http, settings, full=True)

    assert result.created == 2
    assert result.media_failed == 1
    reel = session.scalar(select(Post).where(Post.dedupe_key == "ig:17900000000000004"))
    assert reel.media[0].thumbnail_key is None


@respx.mock
def test_missing_media_url_uses_thumbnail(session, settings, ig, storage, http, page1, page2):
    channel = make_channel(session, settings)
    mock_graph(page1, page2)
    mock_cdn()

    result = sync_channel(session, channel, ig, storage, http, settings, full=True)

    post = session.scalar(select(Post).where(Post.dedupe_key == "ig:17900000000000004"))
    assert post.media_type == "VIDEO"
    assert len(post.media) == 1
    assert post.media[0].storage_key is None
    assert post.media[0].thumbnail_key == "instagram/test-org/17900000000000004_thumb.jpg"
    assert storage.open(post.media[0].thumbnail_key) == IMAGE_BYTES
    assert result.media_failed == 0  # 미디어 URL이 원래 없는 것은 실패가 아니다


@respx.mock
def test_auth_error_mid_pagination(session, settings, ig, storage, http, page1):
    channel = make_channel(session, settings)
    respx.get(f"{BASE}/me/media").mock(return_value=httpx.Response(200, json=page1))
    respx.get(page1["paging"]["next"]).mock(
        return_value=httpx.Response(400, json={"error": {"code": 190, "message": "expired"}})
    )
    mock_cdn()

    result = sync_channel(session, channel, ig, storage, http, settings, full=True)

    assert result.error == "needs_reauth"
    assert result.created == 3
    assert channel.status == "needs_reauth"
    assert channel.last_synced_at is None
    session.rollback()  # 커밋되지 않은 것은 사라진다
    assert len(session.scalars(select(Post)).all()) == 3


@respx.mock
def test_rate_limit_keeps_status(session, settings, ig, storage, http):
    channel = make_channel(session, settings)
    respx.get(f"{BASE}/me/media").mock(
        return_value=httpx.Response(429, json={"error": {"code": 4, "message": "slow down"}})
    )

    result = sync_channel(session, channel, ig, storage, http, settings)

    assert result.error == "rate_limited"
    assert channel.status == "active"
    assert channel.last_synced_at is None


@respx.mock
def test_other_api_error_is_failed(session, settings, ig, storage, http):
    channel = make_channel(session, settings)
    respx.get(f"{BASE}/me/media").mock(return_value=httpx.Response(500))

    result = sync_channel(session, channel, ig, storage, http, settings)

    assert result.error == "failed"
    assert channel.status == "active"


def test_undecryptable_token_is_failed(session, settings, ig, storage, http):
    channel = make_channel(session, settings)
    channel.access_token_enc = "not-a-valid-token"
    session.commit()

    result = sync_channel(session, channel, ig, storage, http, settings)

    assert result.error == "failed"


def test_missing_token_needs_reauth(session, settings, ig, storage, http):
    channel = make_channel(session, settings)
    channel.access_token_enc = None
    session.commit()

    result = sync_channel(session, channel, ig, storage, http, settings)

    assert result.error == "needs_reauth"


@respx.mock
def test_sync_all_continues_after_channel_failure(session, settings, ig, storage, http, page2):
    bad = make_channel(session, settings, slug="org-a", handle="dummy_a", ext_id="1")
    good = make_channel(session, settings, slug="org-b", handle="dummy_b", ext_id="2")
    bad.access_token_enc = encrypt_token(settings, "BAD")
    good.access_token_enc = encrypt_token(settings, "GOOD")
    session.commit()

    def graph(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("access_token") == "BAD":
            return httpx.Response(400, json={"error": {"code": 190, "message": "expired"}})
        return httpx.Response(200, json=page2)

    respx.get(f"{BASE}/me/media").mock(side_effect=graph)
    mock_cdn()

    results = sync_all(session, ig, storage, http, settings)

    assert results["dummy_a"].error == "needs_reauth"
    assert results["dummy_b"].error is None
    assert results["dummy_b"].created > 0
    assert bad.status == "needs_reauth"


@respx.mock
def test_sync_all_filters_org_and_skips_inactive(session, settings, ig, storage, http, page2):
    make_channel(session, settings, slug="org-a", handle="dummy_a", ext_id="1")
    make_channel(session, settings, slug="org-b", handle="dummy_b", ext_id="2")
    inactive = make_channel(session, settings, slug="org-c", handle="dummy_c", ext_id="3")
    inactive.status = "needs_reauth"
    session.commit()
    respx.get(f"{BASE}/me/media").mock(return_value=httpx.Response(200, json=page2))
    mock_cdn()

    assert set(sync_all(session, ig, storage, http, settings)) == {"dummy_a", "dummy_b"}
    assert set(sync_all(session, ig, storage, http, settings, org_slug="org-b")) == {"dummy_b"}


@respx.mock
def test_sync_all_skips_disconnected_channel(session, settings, ig, storage, http, page2):
    make_channel(session, settings, slug="org-a", handle="dummy_a", ext_id="1")
    gone = make_channel(session, settings, slug="org-b", handle="dummy_b", ext_id="2")
    gone.status = "disconnected"
    gone.access_token_enc = None
    gone.token_expires_at = None
    session.commit()
    respx.get(f"{BASE}/me/media").mock(return_value=httpx.Response(200, json=page2))
    mock_cdn()

    assert set(sync_all(session, ig, storage, http, settings)) == {"dummy_a"}
    session.refresh(gone)
    assert gone.status == "disconnected"


@respx.mock
def test_sync_all_survives_unexpected_exception(session, settings, ig, http, page2):
    make_channel(session, settings, slug="org-a", handle="dummy_a", ext_id="1")
    make_channel(session, settings, slug="org-b", handle="dummy_b", ext_id="2")

    class ExplodingStorage:
        def __init__(self):
            self.calls = 0

        def put(self, key, data, content_type):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("disk full")

    respx.get(f"{BASE}/me/media").mock(return_value=httpx.Response(200, json=page2))
    mock_cdn()

    results = sync_all(session, ig, ExplodingStorage(), http, settings)

    assert results["dummy_a"].error == "failed"
    assert results["dummy_b"].error is None
    assert results["dummy_b"].created > 0
