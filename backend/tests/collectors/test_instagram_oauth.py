import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import respx
from sqlalchemy import select

from app.collectors.instagram.client import InstagramClient
from app.collectors.instagram.oauth import build_connect_url, refresh_expiring
from app.models import Channel, Organization
from app.security import decrypt_token, encrypt_token, sign_state, verify_state

GRAPH = "https://graph.instagram.com"
BASE = f"{GRAPH}/v26.0"
TOKEN_URL = "https://api.instagram.com/oauth/access_token"
CALLBACK = "/integrations/instagram/callback"


def make_org(session, slug="test-org") -> Organization:
    org = Organization(slug=slug, name="테스트 조직", kind="student_council", department="테스트학과")
    session.add(org)
    session.commit()
    return org


def mock_oauth(long_token="L", user_id="111", username="dummy_account", expires_in=5184000):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "S", "user_id": user_id}))
    respx.get(f"{GRAPH}/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": long_token, "expires_in": expires_in})
    )
    respx.get(f"{BASE}/me").mock(return_value=httpx.Response(200, json={"user_id": user_id, "username": username}))
    respx.get(f"{BASE}/me/media").mock(return_value=httpx.Response(200, json={"data": []}))


def callback(client, settings, slug="test-org", code="CODE"):
    return client.get(CALLBACK, params={"code": code, "state": sign_state(settings, slug)})


def channels(session) -> list[Channel]:
    session.expire_all()
    return list(session.scalars(select(Channel).order_by(Channel.id)))


def make_ig(http) -> InstagramClient:
    return InstagramClient(http, "id", "secret", "v26.0", sleep=lambda s: None)


def test_connect_url_params(settings):
    url = build_connect_url(settings, "test-org")

    parsed = urlparse(url)
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://www.instagram.com/oauth/authorize"
    assert query["client_id"] == settings.instagram_app_id
    assert query["redirect_uri"] == settings.instagram_redirect_uri
    assert query["response_type"] == "code"
    assert query["scope"] == "instagram_business_basic"
    assert verify_state(settings, query["state"]) == "test-org"


@respx.mock
def test_callback_creates_channel(client, session, settings):
    make_org(session)
    mock_oauth()

    r = callback(client, settings)

    assert r.status_code == 200
    assert "연동 완료" in r.text
    [channel] = channels(session)
    assert channel.handle == "dummy_account"
    assert channel.external_user_id == "111"
    assert channel.status == "active"
    assert channel.access_token_enc != "L"
    assert decrypt_token(settings, channel.access_token_enc) == "L"
    assert channel.token_expires_at is not None
    assert channel.last_synced_at is not None  # 백그라운드 전체 수집이 돌았다


@respx.mock
def test_callback_strips_trailing_hash_underscore(client, session, settings):
    make_org(session)
    mock_oauth()

    r = callback(client, settings, code="CODE#_")

    assert r.status_code == 200
    body = respx.calls[0].request.content.decode()
    assert "code=CODE&" in body + "&"
    assert "%23" not in body


@respx.mock
def test_reconnect_same_account_replaces_token(client, session, settings):
    make_org(session)
    mock_oauth(long_token="L1")
    assert callback(client, settings).status_code == 200
    mock_oauth(long_token="L2", username="renamed_account")

    assert callback(client, settings).status_code == 200

    [channel] = channels(session)
    assert decrypt_token(settings, channel.access_token_enc) == "L2"
    assert channel.handle == "renamed_account"


@respx.mock
def test_reconnect_reactivates_needs_reauth(client, session, settings):
    make_org(session)
    mock_oauth()
    assert callback(client, settings).status_code == 200
    [channel] = channels(session)
    channel.status = "needs_reauth"
    session.commit()

    assert callback(client, settings).status_code == 200

    assert channels(session)[0].status == "active"


@respx.mock
def test_reconnect_after_disconnect_reactivates_in_same_org(client, session, settings):
    make_org(session)
    mock_oauth(long_token="L1")
    assert callback(client, settings).status_code == 200
    [channel] = channels(session)
    channel.status = "disconnected"
    channel.access_token_enc = None
    channel.token_expires_at = None
    session.commit()
    channel_id = channel.id
    mock_oauth(long_token="L2", username="renamed_account")

    assert callback(client, settings).status_code == 200

    session.expire_all()
    [channel] = channels(session)
    assert channel.id == channel_id
    assert channel.status == "active"
    assert channel.handle == "renamed_account"
    assert decrypt_token(settings, channel.access_token_enc) == "L2"
    assert channel.token_expires_at is not None


@respx.mock
def test_disconnected_channel_in_other_org_conflict(client, session, settings):
    make_org(session, "org-a")
    make_org(session, "org-b")
    mock_oauth()
    assert callback(client, settings, slug="org-a").status_code == 200
    [channel] = channels(session)
    channel.status = "disconnected"
    channel.access_token_enc = None
    session.commit()

    r = callback(client, settings, slug="org-b")

    assert r.status_code == 409
    [channel] = channels(session)
    assert channel.organization.slug == "org-a"
    assert channel.status == "disconnected"


@respx.mock
def test_same_account_other_org_conflict(client, session, settings):
    make_org(session, "org-a")
    make_org(session, "org-b")
    mock_oauth()
    assert callback(client, settings, slug="org-a").status_code == 200

    r = callback(client, settings, slug="org-b")

    assert r.status_code == 409
    [channel] = channels(session)
    assert channel.organization.slug == "org-a"


@respx.mock
def test_callback_accepts_state_signed_two_days_ago(client, session, settings, monkeypatch):
    make_org(session)
    mock_oauth()
    real_time = time.time
    with monkeypatch.context() as m:
        m.setattr(time, "time", lambda: real_time() - 2 * 86400)
        state = sign_state(settings, "test-org")

    r = client.get(CALLBACK, params={"code": "CODE", "state": state})

    assert r.status_code == 200
    assert len(channels(session)) == 1


@respx.mock
def test_callback_rejects_state_older_than_configured_max_age(client, session, settings, monkeypatch):
    make_org(session)
    mock_oauth()
    real_time = time.time
    with monkeypatch.context() as m:
        m.setattr(time, "time", lambda: real_time() - 4 * 86400)
        state = sign_state(settings, "test-org")

    r = client.get(CALLBACK, params={"code": "CODE", "state": state})

    assert settings.oauth_state_max_age == 259200
    assert r.status_code == 400
    assert channels(session) == []


def test_bad_state_400(client, session):
    make_org(session)

    r = client.get(CALLBACK, params={"code": "CODE", "state": "forged"})

    assert r.status_code == 400
    assert channels(session) == []


def test_unknown_org_404(client, settings):
    assert callback(client, settings, slug="nope").status_code == 404


def test_user_denied_400(client, session):
    make_org(session)

    r = client.get(CALLBACK, params={"error": "access_denied", "error_reason": "user_denied"})

    assert r.status_code == 400
    assert channels(session) == []


@respx.mock
def test_exchange_failure_502_without_secrets(client, session, settings):
    make_org(session)
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(400, json={"error": {"code": 100, "message": "bad"}}))

    r = callback(client, settings)

    assert r.status_code == 502
    assert "instagram.com" not in r.text
    assert channels(session) == []


@respx.mock
def test_refresh_only_expiring(session, settings):
    org = make_org(session)
    now = datetime(2026, 11, 2, tzinfo=timezone.utc)
    soon = Channel(
        organization_id=org.id, handle="soon", external_user_id="1", status="active",
        access_token_enc=encrypt_token(settings, "OLD-SOON"), token_expires_at=now + timedelta(days=5),
    )
    later = Channel(
        organization_id=org.id, handle="later", external_user_id="2", status="active",
        access_token_enc=encrypt_token(settings, "OLD-LATER"), token_expires_at=now + timedelta(days=30),
    )
    session.add_all([soon, later])
    session.commit()
    route = respx.get(f"{GRAPH}/refresh_access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "NEW", "expires_in": 5184000})
    )

    with httpx.Client() as http:
        count = refresh_expiring(session, make_ig(http), settings, now)

    assert count == 1
    assert route.call_count == 1
    session.expire_all()
    assert decrypt_token(settings, soon.access_token_enc) == "NEW"
    assert soon.token_expires_at > now + timedelta(days=30)
    assert decrypt_token(settings, later.access_token_enc) == "OLD-LATER"


@respx.mock
def test_refresh_auth_error_marks_needs_reauth_and_continues(session, settings):
    org = make_org(session)
    now = datetime(2026, 11, 2, tzinfo=timezone.utc)
    bad = Channel(
        organization_id=org.id, handle="bad", external_user_id="1", status="active",
        access_token_enc=encrypt_token(settings, "BAD"), token_expires_at=now + timedelta(days=1),
    )
    good = Channel(
        organization_id=org.id, handle="good", external_user_id="2", status="active",
        access_token_enc=encrypt_token(settings, "GOOD"), token_expires_at=now + timedelta(days=2),
    )
    skipped = Channel(  # 이미 재연동이 필요한 채널은 건드리지 않는다
        organization_id=org.id, handle="skipped", external_user_id="3", status="needs_reauth",
        access_token_enc=encrypt_token(settings, "X"), token_expires_at=now + timedelta(days=1),
    )
    session.add_all([bad, good, skipped])
    session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["access_token"] == "BAD":
            return httpx.Response(400, json={"error": {"code": 190, "message": "expired"}})
        return httpx.Response(200, json={"access_token": "NEW", "expires_in": 5184000})

    respx.get(f"{GRAPH}/refresh_access_token").mock(side_effect=handler)

    with httpx.Client() as http:
        count = refresh_expiring(session, make_ig(http), settings, now)

    assert count == 1
    session.expire_all()
    assert bad.status == "needs_reauth"
    assert good.status == "active"
    assert decrypt_token(settings, good.access_token_enc) == "NEW"
    assert decrypt_token(settings, skipped.access_token_enc) == "X"


@respx.mock
def test_refresh_other_errors_skip_and_keep_status(session, settings):
    org = make_org(session)
    now = datetime(2026, 11, 2, tzinfo=timezone.utc)
    undecryptable = Channel(
        organization_id=org.id, handle="b", external_user_id="2", status="active",
        access_token_enc="not-a-fernet-token", token_expires_at=now + timedelta(days=1),
    )
    api_fail = Channel(
        organization_id=org.id, handle="a", external_user_id="1", status="active",
        access_token_enc=encrypt_token(settings, "OLD"), token_expires_at=now + timedelta(days=1),
    )
    session.add_all([undecryptable, api_fail])
    session.commit()
    respx.get(f"{GRAPH}/refresh_access_token").mock(return_value=httpx.Response(500, json={}))

    with httpx.Client() as http:
        count = refresh_expiring(session, make_ig(http), settings, now)

    assert count == 0
    session.expire_all()
    assert api_fail.status == "active" and undecryptable.status == "active"
    assert decrypt_token(settings, api_fail.access_token_enc) == "OLD"
