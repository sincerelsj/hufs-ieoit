import time
from urllib.parse import parse_qs, urlparse

import httpx
import respx
from sqlalchemy import select

from app.collectors.instagram.oauth import build_connect_url
from app.models import Channel, Organization
from app.security import decrypt_token, sign_state, verify_state

BASE = "https://graph.facebook.com/v26.0"
TOKEN_URL = f"{BASE}/oauth/access_token"
ACCOUNTS_URL = f"{BASE}/me/assigned_instagram_accounts"
CALLBACK = "/integrations/instagram/callback"


def make_org(session, slug="test-org") -> Organization:
    org = Organization(slug=slug, name="테스트 조직", kind="student_council", department="테스트학과")
    session.add(org)
    session.commit()
    return org


def mock_oauth(token="L", user_id="111", username="dummy_account", accounts=None):
    if accounts is None:
        accounts = [{"id": user_id, "username": username}]
    respx.get(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": token}))
    respx.get(ACCOUNTS_URL).mock(return_value=httpx.Response(200, json={"data": accounts}))
    respx.get(url__regex=rf"^{BASE}/[0-9]+/media").mock(return_value=httpx.Response(200, json={"data": []}))


def callback(client, settings, slug="test-org", code="CODE"):
    return client.get(CALLBACK, params={"code": code, "state": sign_state(settings, slug)})


def channels(session) -> list[Channel]:
    session.expire_all()
    return list(session.scalars(select(Channel).order_by(Channel.id)))


def test_connect_url_params(settings):
    url = build_connect_url(settings, "test-org")

    parsed = urlparse(url)
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://www.facebook.com/dialog/oauth"
    assert query["client_id"] == settings.instagram_app_id
    assert query["config_id"] == settings.instagram_config_id
    assert query["redirect_uri"] == settings.instagram_redirect_uri
    assert query["response_type"] == "code"
    assert "scope" not in query  # Unified login은 권한을 config_id의 구성으로 정한다.
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
    assert channel.token_expires_at is None  # 시스템 사용자 토큰은 만료되지 않는다.
    assert channel.last_synced_at is not None  # 백그라운드 전체 수집이 돌았다


@respx.mock
def test_callback_strips_trailing_hash_underscore(client, session, settings):
    make_org(session)
    mock_oauth()

    r = callback(client, settings, code="CODE#_")

    assert r.status_code == 200
    assert respx.calls[0].request.url.params["code"] == "CODE"


@respx.mock
def test_reconnect_same_account_replaces_token(client, session, settings):
    make_org(session)
    mock_oauth(token="L1")
    assert callback(client, settings).status_code == 200
    mock_oauth(token="L2", username="renamed_account")

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
    mock_oauth(token="L1")
    assert callback(client, settings).status_code == 200
    [channel] = channels(session)
    channel.status = "disconnected"
    channel.access_token_enc = None
    channel.token_expires_at = None
    session.commit()
    channel_id = channel.id
    mock_oauth(token="L2", username="renamed_account")

    assert callback(client, settings).status_code == 200

    session.expire_all()
    [channel] = channels(session)
    assert channel.id == channel_id
    assert channel.status == "active"
    assert channel.handle == "renamed_account"
    assert decrypt_token(settings, channel.access_token_enc) == "L2"


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
    respx.get(TOKEN_URL).mock(return_value=httpx.Response(400, json={"error": {"code": 100, "message": "bad"}}))

    r = callback(client, settings)

    assert r.status_code == 502
    assert "facebook.com" not in r.text
    assert channels(session) == []


@respx.mock
def test_callback_connects_every_shared_account(client, session, settings):
    make_org(session)
    mock_oauth(accounts=[{"id": "111", "username": "dummy_a"}, {"id": "222", "username": "dummy_b"}])

    assert callback(client, settings).status_code == 200

    assert [(c.handle, c.external_user_id) for c in channels(session)] == [("dummy_a", "111"), ("dummy_b", "222")]
    assert all(c.last_synced_at is not None for c in channels(session))


@respx.mock
def test_callback_without_shared_account_400(client, session, settings):
    make_org(session)
    mock_oauth(accounts=[])

    r = callback(client, settings)

    assert r.status_code == 400
    assert channels(session) == []
