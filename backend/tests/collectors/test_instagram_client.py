import json
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
BASE = "https://graph.facebook.com/v26.0"
# 샘플 paging.next의 계정 ID(178000...)와 달라야 첫 페이지 route가 다음 페이지를 가로채지 않는다.
IG_ID = "17841400000000000"
MEDIA = f"{BASE}/{IG_ID}/media"
ACCOUNTS = f"{BASE}/me/assigned_instagram_accounts"
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
    first = respx.get(MEDIA).mock(return_value=httpx.Response(200, json=page1))
    second = respx.get(next_url).mock(return_value=httpx.Response(200, json=page2))

    items = list(client.iter_media("tok", IG_ID))

    assert len(items) == len(page1["data"]) + len(page2["data"])
    assert items[-1]["id"] == "17900000000000005"
    assert first.call_count == 1 and second.call_count == 1
    assert len(respx.calls) == 2


@respx.mock
def test_iter_media_sends_fields(client):
    route = respx.get(MEDIA).mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    assert list(client.iter_media("tok", IG_ID)) == []

    params = route.calls[0].request.url.params
    assert params["fields"] == MEDIA_FIELDS
    assert params["limit"] == "50"
    assert params["access_token"] == "tok"


@respx.mock
def test_auth_error_190(client):
    respx.get(MEDIA).mock(
        return_value=httpx.Response(
            400, json={"error": {"code": 190, "message": "Invalid OAuth access token."}}
        )
    )

    with pytest.raises(InstagramAuthError) as exc:
        list(client.iter_media(SECRET_TOKEN, IG_ID))
    assert SECRET_TOKEN not in str(exc.value)


@respx.mock
def test_rate_limit_retries_then_raises(client, sleeps):
    route = respx.get(ACCOUNTS).mock(return_value=httpx.Response(429))

    with pytest.raises(InstagramRateLimitError) as exc:
        client.assigned_accounts(SECRET_TOKEN)

    assert sleeps == [1, 2, 4]
    assert route.call_count == 4
    assert SECRET_TOKEN not in str(exc.value)


@respx.mock
def test_rate_limit_by_error_code_retries(client, sleeps):
    respx.get(ACCOUNTS).mock(
        return_value=httpx.Response(400, json={"error": {"code": 4, "message": "limit"}})
    )

    with pytest.raises(InstagramRateLimitError):
        client.assigned_accounts("tok")
    assert sleeps == [1, 2, 4]


@respx.mock
def test_rate_limit_recovers(client, sleeps):
    respx.get(ACCOUNTS).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, json={"data": [{"id": "123", "username": "dummy_account"}]}),
        ]
    )

    assert client.assigned_accounts("tok") == [{"id": "123", "username": "dummy_account"}]
    assert sleeps == [1]


@respx.mock
def test_other_error_raises_instagram_error(client, sleeps):
    respx.get(ACCOUNTS).mock(
        return_value=httpx.Response(500, json={"error": {"code": 1, "message": "boom"}})
    )

    with pytest.raises(InstagramError) as exc:
        client.assigned_accounts(SECRET_TOKEN)

    assert not isinstance(exc.value, (InstagramAuthError, InstagramRateLimitError))
    assert "500" in str(exc.value) and "boom" in str(exc.value)
    assert SECRET_TOKEN not in str(exc.value)
    assert sleeps == []


@respx.mock
def test_non_json_error_body(client):
    respx.get(ACCOUNTS).mock(return_value=httpx.Response(502, text="<html>bad gateway</html>"))

    with pytest.raises(InstagramError) as exc:
        client.assigned_accounts("tok")
    assert "502" in str(exc.value)


@respx.mock
def test_assigned_accounts_sends_fields_and_follows_paging(client):
    next_url = f"{ACCOUNTS}?access_token=tok&after=CURSOR"
    first = respx.get(ACCOUNTS, params={"fields": "id,username"}).mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": "1", "username": "dummy_a"}], "paging": {"next": next_url}}
        )
    )
    respx.get(next_url).mock(
        return_value=httpx.Response(200, json={"data": [{"id": "2", "username": "dummy_b"}]})
    )

    accounts = client.assigned_accounts("tok")

    assert [a["username"] for a in accounts] == ["dummy_a", "dummy_b"]
    assert first.calls[0].request.url.params["access_token"] == "tok"


@respx.mock
def test_exchange_code(client):
    route = respx.get(f"{BASE}/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "SUAT", "token_type": "bearer"})
    )

    assert client.exchange_code("the-code", "https://example.test/cb") == "SUAT"

    assert dict(route.calls[0].request.url.params) == {
        "client_id": "app-id",
        "client_secret": "app-secret",
        "redirect_uri": "https://example.test/cb",
        "code": "the-code",
    }


@respx.mock
def test_timeout_is_retried_then_succeeds(client, sleeps):
    route = respx.get(MEDIA).mock(side_effect=[
        httpx.ReadTimeout("slow"),
        httpx.Response(200, json={"data": []}),
    ])

    assert list(client.iter_media("tok", IG_ID)) == []

    assert route.call_count == 2
    assert sleeps == [1]


@respx.mock
def test_timeout_gives_up_without_url_in_message(client, sleeps):
    respx.get(MEDIA).mock(side_effect=httpx.ReadTimeout("slow"))

    with pytest.raises(InstagramError) as exc:
        list(client.iter_media(SECRET_TOKEN, IG_ID))

    assert "ReadTimeout" in str(exc.value)
    assert SECRET_TOKEN not in str(exc.value)
    assert sleeps == [1, 2, 4]
