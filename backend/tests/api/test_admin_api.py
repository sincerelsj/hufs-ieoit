from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.api.integrations import get_storage
from app.models import Channel, Organization, Post, PostMedia, Term
from app.storage import LocalStorage


def utc(y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


ORG_BODY = {"slug": "council", "name": "테스트 학생회", "kind": "student_council", "department": "테스트학과"}


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/admin/organizations"),
        ("post", "/admin/organizations/council/terms"),
        ("patch", "/admin/organizations/council/terms/1"),
        ("delete", "/admin/organizations/council/terms/1"),
        ("patch", "/admin/posts/1"),
        ("get", "/admin/organizations/council/instagram/connect-url"),
        ("delete", "/admin/channels/1"),
    ],
)
def test_admin_requires_token(client, method, path):
    assert getattr(client, method)(path).status_code == 401
    assert getattr(client, method)(path, headers={"X-Admin-Token": "wrong"}).status_code == 401


# --- 조직 ---


def test_create_organization(client, session, admin):
    r = client.post("/admin/organizations", json=ORG_BODY, headers=admin)
    assert r.status_code == 201
    assert r.json() == ORG_BODY
    assert session.scalar(select(Organization).where(Organization.slug == "council")) is not None


def test_create_organization_duplicate_slug_409(client, admin):
    assert client.post("/admin/organizations", json=ORG_BODY, headers=admin).status_code == 201
    assert client.post("/admin/organizations", json=ORG_BODY, headers=admin).status_code == 409


def test_create_organization_rejects_bad_kind(client, admin):
    r = client.post("/admin/organizations", json={**ORG_BODY, "kind": "bogus"}, headers=admin)
    assert r.status_code == 422


@pytest.mark.parametrize(
    "changes",
    [
        {"slug": ""},
        {"slug": "x" * 101},
        {"slug": "Upper"},
        {"slug": "with_underscore"},
        {"slug": "-leading-hyphen"},
        {"name": ""},
        {"name": "가" * 201},
        {"department": ""},
        {"department": "가" * 201},
    ],
)
def test_create_organization_validates_lengths_and_slug(client, session, admin, changes):
    r = client.post("/admin/organizations", json={**ORG_BODY, **changes}, headers=admin)
    assert r.status_code == 422
    assert session.scalars(select(Organization)).all() == []


def test_create_organization_accepts_max_lengths(client, admin):
    body = {**ORG_BODY, "slug": "a" * 100, "name": "가" * 200, "department": "가" * 200}
    assert client.post("/admin/organizations", json=body, headers=admin).status_code == 201


# --- 임기 ---


def test_create_term_reassigns(client, make_org, make_post, session, admin):
    org = make_org()
    inside = make_post(org, utc(2026, 5, 1))
    outside = make_post(org, utc(2027, 5, 1))
    r = client.post(
        "/admin/organizations/council/terms",
        json={"name": "제1대", "ordinal": 1, "start_date": "2026-03-01", "end_date": "2026-12-31"},
        headers=admin,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "제1대"
    assert body["ordinal"] == 1
    assert body["start_date"] == "2026-03-01"
    assert body["reassigned"] == 1
    session.refresh(inside)
    session.refresh(outside)
    assert inside.term_id == body["id"]
    assert outside.term_id is None


def test_create_term_overlap_409(client, make_org, make_term, admin):
    org = make_org()
    make_term(org, "제1대", date(2026, 3, 1), date(2026, 12, 31))
    r = client.post(
        "/admin/organizations/council/terms",
        json={"name": "겹침", "start_date": "2026-12-31", "end_date": None},
        headers=admin,
    )
    assert r.status_code == 409


def test_create_term_end_before_start_422(client, make_org, admin):
    make_org()
    r = client.post(
        "/admin/organizations/council/terms",
        json={"name": "역전", "start_date": "2026-05-01", "end_date": "2026-04-01"},
        headers=admin,
    )
    assert r.status_code == 422


def test_create_term_unknown_org_404(client, admin):
    r = client.post(
        "/admin/organizations/nope/terms",
        json={"name": "x", "start_date": "2026-05-01"},
        headers=admin,
    )
    assert r.status_code == 404


def test_patch_term_shortened_unassigns_post(client, make_org, make_term, make_post, session, admin):
    org = make_org()
    term = make_term(org, "제1대", date(2026, 3, 1), date(2026, 12, 31))
    post = make_post(org, utc(2026, 10, 1), term=term)
    r = client.patch(
        f"/admin/organizations/council/terms/{term.id}",
        json={"end_date": "2026-08-31"},
        headers=admin,
    )
    assert r.status_code == 200
    assert r.json()["end_date"] == "2026-08-31"
    assert r.json()["reassigned"] == 1
    session.refresh(post)
    assert post.term_id is None


def test_patch_term_partial_keeps_other_fields(client, make_org, make_term, admin):
    org = make_org()
    term = make_term(org, "제1대", date(2026, 3, 1), date(2026, 12, 31))
    r = client.patch(f"/admin/organizations/council/terms/{term.id}", json={"name": "새 이름"}, headers=admin)
    assert r.status_code == 200
    assert r.json()["name"] == "새 이름"
    assert r.json()["start_date"] == "2026-03-01"
    assert r.json()["end_date"] == "2026-12-31"


def test_patch_term_can_clear_end_date(client, make_org, make_term, admin):
    org = make_org()
    term = make_term(org, "제1대", date(2026, 3, 1), date(2026, 12, 31))
    r = client.patch(f"/admin/organizations/council/terms/{term.id}", json={"end_date": None}, headers=admin)
    assert r.status_code == 200
    assert r.json()["end_date"] is None


def test_patch_term_overlap_409_excludes_itself(client, make_org, make_term, admin):
    org = make_org()
    first = make_term(org, "제1대", date(2026, 3, 1), date(2026, 8, 31))
    make_term(org, "제2대", date(2026, 9, 1), None)
    # 자기 자신과는 겹쳐도 된다.
    ok = client.patch(
        f"/admin/organizations/council/terms/{first.id}", json={"end_date": "2026-08-30"}, headers=admin
    )
    assert ok.status_code == 200
    # 다른 임기와 겹치면 409.
    bad = client.patch(
        f"/admin/organizations/council/terms/{first.id}", json={"end_date": "2026-09-01"}, headers=admin
    )
    assert bad.status_code == 409


def test_patch_term_invalid_range_422(client, make_org, make_term, admin):
    org = make_org()
    term = make_term(org, "제1대", date(2026, 3, 1), date(2026, 12, 31))
    r = client.patch(
        f"/admin/organizations/council/terms/{term.id}", json={"end_date": "2026-01-01"}, headers=admin
    )
    assert r.status_code == 422


def test_patch_term_of_other_org_404(client, make_org, make_term, admin):
    make_org()
    term = make_term(make_org("other"))
    r = client.patch(f"/admin/organizations/council/terms/{term.id}", json={"name": "x"}, headers=admin)
    assert r.status_code == 404
    assert client.patch("/admin/organizations/council/terms/9999", json={"name": "x"}, headers=admin).status_code == 404


def test_delete_term_unassigns_and_unlocks_posts(client, make_org, make_term, make_post, session, admin):
    org = make_org()
    term = make_term(org)
    post = make_post(org, utc(2026, 5, 1), term=term)
    post.term_locked = True
    session.commit()
    term_id = term.id
    r = client.delete(f"/admin/organizations/council/terms/{term_id}", headers=admin)
    assert r.status_code == 204
    session.expire_all()
    assert session.get(Term, term_id) is None
    assert post.term_id is None
    assert post.term_locked is False


def test_delete_term_of_other_org_404(client, make_org, make_term, admin):
    make_org()
    term = make_term(make_org("other"))
    assert client.delete(f"/admin/organizations/council/terms/{term.id}", headers=admin).status_code == 404


# --- 게시물 ---


def test_patch_post_sets_term_and_lock(client, make_org, make_term, make_post, session, admin):
    org = make_org()
    term = make_term(org, "제1대", date(2026, 3, 1), date(2026, 8, 31))
    post = make_post(org, utc(2026, 11, 1))  # 임기 밖
    r = client.patch(f"/admin/posts/{post.id}", json={"term_id": term.id, "term_locked": True}, headers=admin)
    assert r.status_code == 200
    assert r.json()["term_id"] == term.id
    assert r.json()["term_locked"] is True
    assert "raw_payload" not in r.json()
    session.refresh(post)
    assert (post.term_id, post.term_locked) == (term.id, True)


def test_patch_post_clear_term(client, make_org, make_term, make_post, admin):
    org = make_org()
    term = make_term(org)
    post = make_post(org, utc(2026, 5, 1), term=term)
    r = client.patch(f"/admin/posts/{post.id}", json={"term_id": None, "term_locked": True}, headers=admin)
    assert r.status_code == 200
    assert r.json()["term_id"] is None


def test_patch_post_term_of_other_org_422(client, make_org, make_term, make_post, admin):
    org = make_org()
    foreign = make_term(make_org("other"))
    post = make_post(org, utc(2026, 5, 1))
    r = client.patch(f"/admin/posts/{post.id}", json={"term_id": foreign.id, "term_locked": True}, headers=admin)
    assert r.status_code == 422


def test_patch_post_unknown_ids(client, make_org, make_post, admin):
    org = make_org()
    body = {"term_id": None, "term_locked": False}
    assert client.patch("/admin/posts/9999", json=body, headers=admin).status_code == 404
    post = make_post(org, utc(2026, 5, 1))
    r = client.patch(f"/admin/posts/{post.id}", json={"term_id": 9999, "term_locked": False}, headers=admin)
    assert r.status_code == 422


def test_patch_post_masks_caption(client, make_org, make_post, admin):
    org = make_org()
    post = make_post(org, utc(2026, 5, 1), caption="010-1234-5678")
    r = client.patch(f"/admin/posts/{post.id}", json={"term_id": None, "term_locked": False}, headers=admin)
    assert r.json()["caption"] == "010-****-****"


def test_term_name_validation_422(client, make_org, make_term, admin):
    org = make_org()
    term = make_term(org)
    base = {"start_date": "2030-03-01"}
    assert client.post("/admin/organizations/council/terms", json={**base, "name": ""}, headers=admin).status_code == 422
    assert (
        client.post("/admin/organizations/council/terms", json={**base, "name": "가" * 201}, headers=admin).status_code
        == 422
    )
    assert client.patch(f"/admin/organizations/council/terms/{term.id}", json={"name": ""}, headers=admin).status_code == 422
    assert (
        client.patch(
            f"/admin/organizations/council/terms/{term.id}", json={"name": "가" * 201}, headers=admin
        ).status_code
        == 422
    )


# --- 연결 링크 ---


def test_connect_url(client, make_org, admin):
    make_org()
    r = client.get("/admin/organizations/council/instagram/connect-url", headers=admin)
    assert r.status_code == 200
    query = parse_qs(urlparse(r.json()["url"]).query)
    assert query["client_id"] == ["test-app-id"]
    assert "state" in query


@pytest.mark.parametrize(
    "field,env_name",
    [
        ("state_secret", "STATE_SECRET"),
        ("instagram_app_id", "INSTAGRAM_APP_ID"),
        ("instagram_app_secret", "INSTAGRAM_APP_SECRET"),
        ("instagram_redirect_uri", "INSTAGRAM_REDIRECT_URI"),
        ("token_encryption_key", "TOKEN_ENCRYPTION_KEY"),
    ],
)
def test_connect_url_503_when_setting_empty(client, settings, make_org, admin, field, env_name):
    make_org()
    secret_values = {settings.state_secret, settings.instagram_app_secret, settings.token_encryption_key}
    setattr(settings, field, "")
    r = client.get("/admin/organizations/council/instagram/connect-url", headers=admin)
    assert r.status_code == 503
    assert env_name in r.json()["detail"]
    assert not any(v and v in r.text for v in secret_values)


def test_connect_url_503_when_fernet_key_invalid(client, settings, make_org, admin):
    make_org()
    settings.token_encryption_key = "not-a-valid-fernet-key"
    r = client.get("/admin/organizations/council/instagram/connect-url", headers=admin)
    assert r.status_code == 503
    assert "TOKEN_ENCRYPTION_KEY" in r.json()["detail"]
    assert "not-a-valid-fernet-key" not in r.text


def test_connect_url_unknown_org_404(client, admin):
    assert client.get("/admin/organizations/nope/instagram/connect-url", headers=admin).status_code == 404


# --- 채널 삭제 ---


@pytest.fixture
def storage(client, tmp_path):
    store = LocalStorage(tmp_path / "purge-media")
    client.app.dependency_overrides[get_storage] = lambda: store
    return store


def _channel_with_posts(session, make_org, make_post, storage):
    org = make_org()
    channel = Channel(organization_id=org.id, platform="instagram", handle="dummy", external_user_id="u1")
    session.add(channel)
    session.commit()
    for key in ("a.jpg", "a_t.jpg", "b.mp4"):
        storage.put(f"instagram/council/{key}", b"data", "application/octet-stream")
    media = [
        PostMedia(
            position=0,
            media_type="IMAGE",
            storage_key="instagram/council/a.jpg",
            thumbnail_key="instagram/council/a_t.jpg",
        ),
        PostMedia(position=1, media_type="VIDEO", storage_key="instagram/council/b.mp4", thumbnail_key=None),
        PostMedia(position=2, media_type="IMAGE", storage_key=None, thumbnail_key=None),
    ]
    post = make_post(org, utc(2026, 5, 1), channel=channel, media=media)
    other = make_post(org, utc(2026, 6, 1))  # 채널 없는 게시물은 건드리지 않는다.
    return channel, post, other


def test_delete_channel_purge(client, session, make_org, make_post, storage, admin):
    channel, post, other = _channel_with_posts(session, make_org, make_post, storage)
    channel_id, post_id, other_id = channel.id, post.id, other.id
    r = client.delete(f"/admin/channels/{channel_id}?purge=true", headers=admin)
    assert r.status_code == 200
    assert r.json() == {"deleted_posts": 1}
    session.expire_all()
    assert session.get(Channel, channel_id) is None
    assert session.get(Post, post_id) is None
    assert session.get(Post, other_id) is not None
    assert session.scalars(select(PostMedia)).all() == []
    for key in ("a.jpg", "a_t.jpg", "b.mp4"):
        with pytest.raises(FileNotFoundError):
            storage.open(f"instagram/council/{key}")


def test_delete_channel_without_purge_disconnects_and_keeps_posts(
    client, session, make_org, make_post, storage, admin
):
    channel, post, _ = _channel_with_posts(session, make_org, make_post, storage)
    channel.access_token_enc = "dummy-encrypted"
    channel.token_expires_at = utc(2026, 12, 1)
    session.commit()
    channel_id, post_id = channel.id, post.id
    r = client.delete(f"/admin/channels/{channel_id}", headers=admin)
    assert r.status_code == 200
    assert r.json() == {"deleted_posts": 0}
    session.expire_all()
    kept_channel = session.get(Channel, channel_id)
    assert kept_channel is not None
    assert kept_channel.status == "disconnected"
    assert kept_channel.access_token_enc is None
    assert kept_channel.token_expires_at is None
    kept = session.get(Post, post_id)
    assert kept is not None
    assert kept.channel_id == channel_id
    assert len(kept.media) == 3
    assert storage.open("instagram/council/a.jpg") == b"data"


def test_purge_after_disconnect_deletes_records(client, session, make_org, make_post, storage, admin):
    channel, post, other = _channel_with_posts(session, make_org, make_post, storage)
    channel_id, post_id, other_id = channel.id, post.id, other.id
    assert client.delete(f"/admin/channels/{channel_id}", headers=admin).status_code == 200

    r = client.delete(f"/admin/channels/{channel_id}?purge=true", headers=admin)

    assert r.status_code == 200
    assert r.json() == {"deleted_posts": 1}
    session.expire_all()
    assert session.get(Channel, channel_id) is None
    assert session.get(Post, post_id) is None
    assert session.get(Post, other_id) is not None
    assert session.scalars(select(PostMedia)).all() == []
    with pytest.raises(FileNotFoundError):
        storage.open("instagram/council/a.jpg")


def test_delete_channel_unknown_404(client, storage, admin):
    assert client.delete("/admin/channels/9999?purge=true", headers=admin).status_code == 404
