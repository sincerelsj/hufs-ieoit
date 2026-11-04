import httpx
import pytest
import respx
from sqlalchemy import select

from app.collectors.instagram.client import (
    DISCOVERY_MEDIA_FIELDS,
    InstagramAuthError,
    InstagramClient,
    InstagramError,
)
from app.collectors.instagram.discovery import (
    CollectorAccountNotFound,
    CollectorNotRegistered,
    add_discovery_channel,
    get_collector,
    register_collector,
)
from app.collectors.instagram.oauth import ChannelConflict
from app.collectors.instagram.sync import sync_channel
from app.models import Channel, CollectorCredential, Organization, Post
from app.security import decrypt_token, encrypt_token
from app.storage import LocalStorage

BASE = "https://graph.facebook.com/v26.0"
COLLECTOR_ID = "17841400000000001"
COLLECTOR = f"{BASE}/{COLLECTOR_ID}"
CDN = "https://cdn.example.test/media"


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def http():
    with httpx.Client() as c:
        yield c


@pytest.fixture
def ig(http, settings, sleeps) -> InstagramClient:
    return InstagramClient(
        http, settings.instagram_app_id, settings.instagram_app_secret,
        settings.instagram_api_version, sleep=sleeps.append,
    )


def item(n: int, day: int) -> dict:
    return {
        "id": f"1790000000000{n:04d}",
        "caption": f"더미 캡션 {n}",
        "media_type": "IMAGE",
        "media_url": f"{CDN}/{n}.jpg",
        "permalink": f"https://www.instagram.com/p/DUMMY{n}/",
        "timestamp": f"2026-10-{day:02d}T09:00:00+0000",
        "username": "dummy_target",
    }


def discovery_page(items: list[dict], after: str | None) -> dict:
    """실제 응답처럼 paging에는 cursors.after만 있고 next는 없다."""
    media: dict = {"data": items}
    if after:
        media["paging"] = {"cursors": {"after": after}}
    return {"business_discovery": {"media": media, "id": "17841400000000009"}, "id": COLLECTOR_ID}


def mock_discovery(pages: dict[str | None, dict]):
    """after 커서(None = 첫 페이지)별로 다른 응답을 준다."""

    def respond(request: httpx.Request) -> httpx.Response:
        fields = request.url.params["fields"]
        for after, body in pages.items():
            if after is None and "media.after(" not in fields:
                return httpx.Response(200, json=body)
            if after is not None and f"media.after({after})" in fields:
                return httpx.Response(200, json=body)
        return httpx.Response(500)

    return respx.get(COLLECTOR).mock(side_effect=respond)


# --- client ---------------------------------------------------------------


@respx.mock
def test_iter_discovered_media_follows_cursor(ig, sleeps):
    route = mock_discovery({
        None: discovery_page([item(1, 20), item(2, 19)], after="CUR1"),
        "CUR1": discovery_page([item(3, 18)], after=None),
    })

    items = list(ig.iter_discovered_media("tok", COLLECTOR_ID, "dummy_target", page_size=2))

    assert [i["id"][-1] for i in items] == ["1", "2", "3"]
    assert route.call_count == 2
    first = route.calls[0].request.url.params
    assert first["fields"] == (
        f"business_discovery.username(dummy_target){{media.limit(2){{{DISCOVERY_MEDIA_FIELDS}}}}}"
    )
    assert first["access_token"] == "tok"
    assert sleeps == [1.0]  # 페이지 사이 간격


@respx.mock
def test_iter_discovered_media_stops_on_empty_page_or_same_cursor(ig):
    route = mock_discovery({
        None: discovery_page([item(1, 20)], after="CUR1"),
        "CUR1": discovery_page([item(2, 19)], after="CUR2"),
        "CUR2": discovery_page([], after="CUR3"),  # 마지막 뒤 빈 페이지에도 커서가 올 수 있다
    })

    items = list(ig.iter_discovered_media("tok", COLLECTOR_ID, "dummy_target"))

    assert len(items) == 2 and route.call_count == 3


@respx.mock
def test_iter_discovered_media_stops_when_cursor_repeats(ig):
    route = mock_discovery({
        None: discovery_page([item(1, 20)], after="CUR1"),
        "CUR1": discovery_page([item(2, 19)], after="CUR1"),
    })

    assert len(list(ig.iter_discovered_media("tok", COLLECTOR_ID, "dummy_target"))) == 2
    assert route.call_count == 2


@respx.mock
def test_discover_account_returns_profile(ig):
    route = respx.get(COLLECTOR).mock(return_value=httpx.Response(200, json={
        "business_discovery": {"id": "17841400000000009", "username": "dummy_target", "media_count": 7},
        "id": COLLECTOR_ID,
    }))

    account = ig.discover_account("tok", COLLECTOR_ID, "dummy_target")

    assert account == {"id": "17841400000000009", "username": "dummy_target", "media_count": 7}
    assert "business_discovery.username(dummy_target)" in route.calls[0].request.url.params["fields"]


@pytest.mark.parametrize("bad", ["a){x}", "has space", "", "a" * 31, "한글"])
def test_discovery_rejects_non_username(ig, bad):
    with pytest.raises(InstagramError):
        ig.discover_account("tok", COLLECTOR_ID, bad)
    with pytest.raises(InstagramError):
        list(ig.iter_discovered_media("tok", COLLECTOR_ID, bad))


@respx.mock
def test_exchange_long_lived_user_token(ig):
    route = respx.get(f"{BASE}/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "LONG", "token_type": "bearer"})
    )

    assert ig.exchange_long_lived_user_token("SHORT") == "LONG"

    params = route.calls[0].request.url.params
    assert params["grant_type"] == "fb_exchange_token"
    assert params["fb_exchange_token"] == "SHORT"
    assert params["client_id"] == "test-app-id"
    assert params["client_secret"] == "test-app-secret"


# --- register / add -------------------------------------------------------


def mock_exchange_and_pages(pages: list[dict]):
    respx.get(f"{BASE}/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "LONG"})
    )
    return respx.get(f"{BASE}/me/accounts").mock(
        return_value=httpx.Response(200, json={"data": pages})
    )


def page(name: str, username: str | None, token: str = "PAGE_TOKEN") -> dict:
    p = {"id": "100", "name": name, "access_token": token}
    if username:
        p["instagram_business_account"] = {"id": f"1784{len(username):011d}", "username": username}
    return p


@respx.mock
def test_register_collector_stores_page_token(session, settings, ig):
    route = mock_exchange_and_pages([page("페이지 없음", None), page("더미 페이지", "dummy_collector")])

    credential = register_collector(session, settings, ig, "SHORT")
    session.commit()

    assert route.calls[0].request.url.params["access_token"] == "LONG"
    assert credential.username == "dummy_collector"
    assert decrypt_token(settings, credential.access_token_enc) == "PAGE_TOKEN"
    assert "PAGE_TOKEN" not in credential.access_token_enc


@respx.mock
def test_register_collector_replaces_previous(session, settings, ig):
    mock_exchange_and_pages([page("더미", "dummy_collector", token="NEW")])
    session.add(CollectorCredential(
        platform="instagram", ig_user_id="1", username="old",
        access_token_enc=encrypt_token(settings, "OLD"),
    ))
    session.commit()

    register_collector(session, settings, ig, "SHORT")
    session.commit()

    rows = session.scalars(select(CollectorCredential)).all()
    assert len(rows) == 1
    assert decrypt_token(settings, rows[0].access_token_enc) == "NEW"


@respx.mock
def test_register_collector_picks_requested_account(session, settings, ig):
    mock_exchange_and_pages([page("A", "dummy_a", token="TA"), page("B", "dummy_b", token="TB")])

    credential = register_collector(session, settings, ig, "SHORT", username="dummy_b")

    assert decrypt_token(settings, credential.access_token_enc) == "TB"


@respx.mock
def test_register_collector_without_linked_page_fails(session, settings, ig):
    mock_exchange_and_pages([page("인스타 미연결", None)])

    with pytest.raises(CollectorAccountNotFound):
        register_collector(session, settings, ig, "SHORT")


def test_get_collector_missing(session):
    with pytest.raises(CollectorNotRegistered):
        get_collector(session)


def make_org(session, slug="test-org") -> Organization:
    org = Organization(slug=slug, name="테스트 조직", kind="student_council", department="테스트학과")
    session.add(org)
    session.flush()
    return org


def test_add_discovery_channel_creates_and_reactivates(session):
    org = make_org(session)
    account = {"id": "17841400000000009", "username": "dummy_target"}

    channel = add_discovery_channel(session, org, account)
    channel.status = "disconnected"
    session.commit()
    again = add_discovery_channel(session, org, account)

    assert again.id == channel.id
    assert again.collect_mode == "discovery"
    assert again.status == "active"
    assert again.access_token_enc is None


def test_add_discovery_channel_conflict(session):
    org_a, org_b = make_org(session, "org-a"), make_org(session, "org-b")
    add_discovery_channel(session, org_a, {"id": "9", "username": "dummy_target"})

    with pytest.raises(ChannelConflict):
        add_discovery_channel(session, org_b, {"id": "9", "username": "dummy_target"})


# --- sync -----------------------------------------------------------------


def make_discovery_setup(session, settings) -> Channel:
    org = make_org(session)
    session.add(CollectorCredential(
        platform="instagram", ig_user_id=COLLECTOR_ID, username="dummy_collector",
        access_token_enc=encrypt_token(settings, "PAGE_TOKEN"),
    ))
    channel = add_discovery_channel(session, org, {"id": "9", "username": "dummy_target"})
    session.commit()
    return channel


@respx.mock
def test_sync_discovery_channel_saves_posts(session, settings, ig, http, tmp_path):
    channel = make_discovery_setup(session, settings)
    route = mock_discovery({
        None: discovery_page([item(1, 20)], after="CUR1"),
        "CUR1": discovery_page([item(2, 19)], after=None),
    })
    respx.get(url__startswith=CDN).mock(
        return_value=httpx.Response(200, content=b"dummy", headers={"content-type": "image/jpeg"})
    )

    result = sync_channel(session, channel, ig, LocalStorage(tmp_path / "s"), http, settings, full=True)

    assert result.error is None and result.created == 2
    assert route.calls[0].request.url.params["access_token"] == "PAGE_TOKEN"
    posts = session.scalars(select(Post).order_by(Post.posted_at)).all()
    assert [p.caption for p in posts] == ["더미 캡션 2", "더미 캡션 1"]
    assert all(p.media[0].storage_key for p in posts)


def test_sync_discovery_without_collector_needs_reauth(session, settings, ig, http, tmp_path):
    org = make_org(session)
    channel = add_discovery_channel(session, org, {"id": "9", "username": "dummy_target"})
    session.commit()

    result = sync_channel(session, channel, ig, LocalStorage(tmp_path / "s"), http, settings)

    assert result.error == "needs_reauth"


@respx.mock
def test_sync_discovery_auth_error_keeps_channel_active(session, settings, ig, http, tmp_path):
    channel = make_discovery_setup(session, settings)
    respx.get(COLLECTOR).mock(
        return_value=httpx.Response(400, json={"error": {"code": 190, "message": "expired"}})
    )

    result = sync_channel(session, channel, ig, LocalStorage(tmp_path / "s"), http, settings)

    assert result.error == "needs_reauth"
    assert session.get(Channel, channel.id).status == "active"


def test_auth_error_type_is_reexported():
    # sync가 잡는 예외와 같은 클래스인지 확인 (discovery 경로도 같은 오류 체계를 쓴다).
    assert issubclass(InstagramAuthError, InstagramError)


@respx.mock
def test_sync_discovery_resumes_from_saved_cursor(session, settings, ig, http, tmp_path):
    channel = make_discovery_setup(session, settings)
    respx.get(url__startswith=CDN).mock(
        return_value=httpx.Response(200, content=b"dummy", headers={"content-type": "image/jpeg"})
    )
    rate_limited = httpx.Response(400, json={"error": {"code": 4, "message": "limit"}})
    calls: list[str] = []

    def first_run(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params["fields"])
        if "media.after(CUR1)" in request.url.params["fields"]:
            return rate_limited
        return httpx.Response(200, json=discovery_page([item(1, 20)], after="CUR1"))

    respx.get(COLLECTOR).mock(side_effect=first_run)
    storage = LocalStorage(tmp_path / "s")

    first = sync_channel(session, channel, ig, storage, http, settings, full=True)

    assert first.error == "rate_limited" and first.created == 1
    assert session.get(Channel, channel.id).sync_cursor == "CUR1"

    respx.reset()
    respx.get(url__startswith=CDN).mock(
        return_value=httpx.Response(200, content=b"dummy", headers={"content-type": "image/jpeg"})
    )
    route = mock_discovery({"CUR1": discovery_page([item(2, 19)], after=None)})

    second = sync_channel(session, session.get(Channel, channel.id), ig, storage, http, settings, full=True)

    assert second.error is None and second.created == 1
    assert route.call_count == 1  # 앞 페이지를 다시 받지 않는다
    assert "media.after(CUR1)" in route.calls[0].request.url.params["fields"]
    assert session.get(Channel, channel.id).sync_cursor is None
    assert len(session.scalars(select(Post)).all()) == 2
