"""Instagram Graph API 클라이언트. HTTP만 알고 DB는 모른다.

보안: 액세스 토큰은 쿼리 파라미터로 전달되므로 요청 URL을 예외 메시지·로그에 넣지 않는다.
"""

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

MEDIA_FIELDS = (
    "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,username,"
    "children{id,media_type,media_url,thumbnail_url}"
)

TOKEN_EXCHANGE_URL = "https://api.instagram.com/oauth/access_token"
GRAPH_HOST = "https://graph.instagram.com"

AUTH_ERROR_CODE = 190
RATE_LIMIT_ERROR_CODES = {4, 17, 32}


class InstagramError(Exception):
    pass


class InstagramAuthError(InstagramError):
    """토큰 만료·취소 (error.code == 190)."""


class InstagramRateLimitError(InstagramError):
    """HTTP 429 또는 error.code in {4, 17, 32}, 재시도 소진 후."""


@dataclass(frozen=True)
class TokenInfo:
    access_token: str
    expires_at: datetime  # aware UTC


class InstagramClient:
    def __init__(
        self,
        http: httpx.Client,
        app_id: str,
        app_secret: str,
        api_version: str,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
    ):
        self._http = http
        self._app_id = app_id
        self._app_secret = app_secret
        self._base = f"{GRAPH_HOST}/{api_version}"
        self._sleep = sleep
        self._max_retries = max_retries

    def iter_media(self, token: str, page_size: int = 50) -> Iterator[dict]:
        url = f"{self._base}/me/media"
        params: dict | None = {
            "fields": MEDIA_FIELDS,
            "limit": str(page_size),
            "access_token": token,
        }
        while url:
            body = self._request("GET", url, params=params)
            yield from body.get("data", [])
            # paging.next는 토큰·커서가 이미 들어 있는 완성된 URL이라 그대로 요청한다.
            url = body.get("paging", {}).get("next")
            params = None

    def me(self, token: str) -> dict:
        return self._request(
            "GET",
            f"{self._base}/me",
            params={"fields": "user_id,username", "access_token": token},
        )

    def exchange_code(self, code: str, redirect_uri: str) -> str:
        body = self._request(
            "POST",
            TOKEN_EXCHANGE_URL,
            data={
                "client_id": self._app_id,
                "client_secret": self._app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        return body["access_token"]

    def exchange_long_lived(self, short_token: str) -> TokenInfo:
        body = self._request(
            "GET",
            f"{GRAPH_HOST}/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": self._app_secret,
                "access_token": short_token,
            },
        )
        return self._token_info(body)

    def refresh(self, token: str) -> TokenInfo:
        body = self._request(
            "GET",
            f"{GRAPH_HOST}/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": token},
        )
        return self._token_info(body)

    @staticmethod
    def _token_info(body: dict) -> TokenInfo:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=body["expires_in"])
        return TokenInfo(access_token=body["access_token"], expires_at=expires_at)

    def _request(self, method: str, url: str, **kwargs) -> dict:
        """모든 호출의 공통 입구: 요청, 오류 해석, 호출 한도 재시도."""
        for attempt in range(self._max_retries + 1):
            try:
                response = self._http.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                # httpx 예외는 URL(토큰 포함)을 담을 수 있어 원인 체인을 끊고 종류만 남긴다.
                raise InstagramError(f"Instagram 요청 실패: {type(exc).__name__}") from None

            if response.is_success:
                return response.json()

            code, message = self._parse_error(response)
            if code == AUTH_ERROR_CODE:
                raise InstagramAuthError(f"토큰이 유효하지 않음 (HTTP {response.status_code}): {message}")
            if response.status_code == 429 or code in RATE_LIMIT_ERROR_CODES:
                if attempt < self._max_retries:
                    self._sleep(2**attempt)
                    continue
                raise InstagramRateLimitError(
                    f"호출 한도 초과, 재시도 {self._max_retries}회 소진 (HTTP {response.status_code}): {message}"
                )
            raise InstagramError(f"Instagram API 오류 (HTTP {response.status_code}): {message}")
        raise AssertionError("unreachable")  # pragma: no cover

    @staticmethod
    def _parse_error(response: httpx.Response) -> tuple[int | None, str]:
        try:
            error = response.json()["error"]
            return error.get("code"), str(error.get("message", ""))
        except (ValueError, KeyError, TypeError, AttributeError):
            return None, ""
