import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import respx

from app.collectors.instagram.client import (
    MEDIA_FIELDS,
    InstagramAuthError,
    InstagramClient,
    InstagramError,
    InstagramRateLimitError,
)

SAMPLES = Path(__file__).resolve().parents[3] / "data" / "samples" / "instagram"
BASE = "https://graph.instagram.com/v26.0"
SECRET_TOKEN = "SECRET_TOKEN_VALUE"


def load_sample(name: str) -> dict:
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def client(sleeps):
    with httpx.Client() as http:
        yield InstagramClient(
            http, app_id="app-id", app_secret="app-secret", api_version="v26.0",
            sleep=sleeps.append,
        )


@respx.mock
def test_iter_media_follows_paging(client):
    page1, page2 = load_sample("media_page1.json"), load_sample("media_page2.json")
    next_url = page1["paging"]["next"]
    first = respx.get(f"{BASE}/me/media").mock(return_value=httpx.Response(200, json=page1))
    second = respx.get(next_url).mock(return_value=httpx.Response(200, json=page2))

    items = list(client.iter_media("tok"))

    assert len(items) == len(page1["data"]) + len(page2["data"])
    assert items[-1]["id"] == "17900000000000005"
    assert first.call_count == 1 and second.call_count == 1
    assert len(respx.calls) == 2


@respx.mock
def test_iter_media_sends_fields(client):
    route = respx.get(f"{BASE}/me/media").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    assert list(client.iter_media("tok")) == []

    params = route.calls[0].request.url.params
    assert params["fields"] == MEDIA_FIELDS
    assert params["limit"] == "50"
    assert params["access_token"] == "tok"


@respx.mock
def test_auth_error_190(client):
    respx.get(f"{BASE}/me/media").mock(
        return_value=httpx.Response(
            400, json={"error": {"code": 190, "message": "Invalid OAuth access token."}}
        )
    )

    with pytest.raises(InstagramAuthError) as exc:
        list(client.iter_media(SECRET_TOKEN))
    assert SECRET_TOKEN not in str(exc.value)


@respx.mock
def test_rate_limit_retries_then_raises(client, sleeps):
    route = respx.get(f"{BASE}/me").mock(return_value=httpx.Response(429))

    with pytest.raises(InstagramRateLimitError) as exc:
        client.me(SECRET_TOKEN)

    assert sleeps == [1, 2, 4]
    assert route.call_count == 4
    assert SECRET_TOKEN not in str(exc.value)


@respx.mock
def test_rate_limit_by_error_code_retries(client, sleeps):
    respx.get(f"{BASE}/me").mock(
        return_value=httpx.Response(400, json={"error": {"code": 4, "message": "limit"}})
    )

    with pytest.raises(InstagramRateLimitError):
        client.me("tok")
    assert sleeps == [1, 2, 4]


@respx.mock
def test_rate_limit_recovers(client, sleeps):
    respx.get(f"{BASE}/me").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, json={"user_id": "123", "username": "dummy_account"}),
        ]
    )

    assert client.me("tok") == {"user_id": "123", "username": "dummy_account"}
    assert sleeps == [1]


@respx.mock
def test_other_error_raises_instagram_error(client, sleeps):
    respx.get(f"{BASE}/me").mock(
        return_value=httpx.Response(500, json={"error": {"code": 1, "message": "boom"}})
    )

    with pytest.raises(InstagramError) as exc:
        client.me(SECRET_TOKEN)

    assert not isinstance(exc.value, (InstagramAuthError, InstagramRateLimitError))
    assert "500" in str(exc.value) and "boom" in str(exc.value)
    assert SECRET_TOKEN not in str(exc.value)
    assert sleeps == []


@respx.mock
def test_non_json_error_body(client):
    respx.get(f"{BASE}/me").mock(return_value=httpx.Response(502, text="<html>bad gateway</html>"))

    with pytest.raises(InstagramError) as exc:
        client.me("tok")
    assert "502" in str(exc.value)


@respx.mock
def test_me_sends_fields(client):
    route = respx.get(f"{BASE}/me").mock(
        return_value=httpx.Response(200, json={"user_id": "1", "username": "u"})
    )

    client.me("tok")

    params = route.calls[0].request.url.params
    assert params["fields"] == "user_id,username"
    assert params["access_token"] == "tok"


@respx.mock
def test_exchange_code(client):
    route = respx.post("https://api.instagram.com/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "SHORT", "user_id": 1})
    )

    assert client.exchange_code("the-code", "https://example.test/cb") == "SHORT"

    form = httpx.QueryParams(route.calls[0].request.content.decode())
    assert dict(form) == {
        "client_id": "app-id",
        "client_secret": "app-secret",
        "grant_type": "authorization_code",
        "redirect_uri": "https://example.test/cb",
        "code": "the-code",
    }


@respx.mock
def test_exchange_long_lived_expiry(client):
    route = respx.get("https://graph.instagram.com/access_token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "L", "token_type": "bearer", "expires_in": 5184000}
        )
    )

    before = datetime.now(timezone.utc)
    info = client.exchange_long_lived("SHORT")
    after = datetime.now(timezone.utc)

    assert info.access_token == "L"
    assert info.expires_at.tzinfo is not None
    assert before + timedelta(days=60) <= info.expires_at <= after + timedelta(days=60)
    params = route.calls[0].request.url.params
    assert params["grant_type"] == "ig_exchange_token"
    assert params["client_secret"] == "app-secret"
    assert params["access_token"] == "SHORT"


@respx.mock
def test_refresh(client):
    route = respx.get("https://graph.instagram.com/refresh_access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "R", "expires_in": 5184000})
    )

    info = client.refresh("OLD")

    assert info.access_token == "R"
    assert info.expires_at > datetime.now(timezone.utc) + timedelta(days=59)
    params = route.calls[0].request.url.params
    assert params["grant_type"] == "ig_refresh_token"
    assert params["access_token"] == "OLD"
