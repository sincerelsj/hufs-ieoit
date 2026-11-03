"""Instagram API(Unified login) 클라이언트. HTTP만 알고 DB는 모른다.

새 Meta 앱은 Instagram 로그인 방식을 쓸 수 없어 Unified login을 쓴다. 모든 호출은 graph.facebook.com으로 간다.
두 가지 수집 방식이 있다.
- 계정 토큰: 수집 대상 계정이 직접 준 토큰으로 /{ig-user-id}/media를 읽는다.
- Business Discovery: 우리 수집용 계정(페이지에 연결된 인스타) 토큰 하나로 다른 공개 프로페셔널 계정을 읽는다.

보안: 액세스 토큰은 쿼리 파라미터로 전달되므로 요청 URL을 예외 메시지·로그에 넣지 않는다.
"""

import re
import time
from collections.abc import Callable, Iterator

import httpx

MEDIA_FIELDS = (
    "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,username,"
    "children{id,media_type,media_url,thumbnail_url}"
)

ACCOUNT_FIELDS = "id,username"

# Business Discovery는 다른 계정의 공개 게시물이라 받을 수 있는 필드가 더 적다(thumbnail_url 없음).
DISCOVERY_MEDIA_FIELDS = (
    "id,caption,media_type,media_url,permalink,timestamp,username,"
    "children{id,media_type,media_url}"
)

DISCOVERY_PAGE_DELAY = 1.0

PAGE_FIELDS ="id,name,access_token,instagram_business_account{id,username}"

GRAPH_HOST = "https://graph.facebook.com"

AUTH_ERROR_CODE = 190
RATE_LIMIT_ERROR_CODES = {4, 17, 32}


class InstagramError(Exception):
    pass


class InstagramAuthError(InstagramError):
    """토큰 만료·취소 (error.code == 190)."""


class InstagramRateLimitError(InstagramError):
    """HTTP 429 또는 error.code in {4, 17, 32}, 재시도 소진 후."""


_USERNAME_RE = re.compile(r"[A-Za-z0-9._]{1,30}")


def _check_username(username: str) -> None:
    """username은 fields 식 안에 들어가므로, 괄호·중괄호로 식을 바꾸지 못하게 인스타 아이디 형식만 허용한다."""
    if not _USERNAME_RE.fullmatch(username):
        raise InstagramError(f"인스타그램 아이디 형식이 아닙니다: {username!r}")


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

    def iter_media(self, token: str, ig_user_id: str, page_size: int = 50) -> Iterator[dict]:
        url = f"{self._base}/{ig_user_id}/media"
        params: dict | None = {
            "fields": MEDIA_FIELDS,
            "limit": str(page_size),
            "access_token": token,
        }
        yield from self._paginate(url, params)

    def assigned_accounts(self, token: str) -> list[dict]:
        """토큰이 접근할 수 있는 Instagram 프로페셔널 계정 목록 ({"id", "username"})."""
        params = {"fields": ACCOUNT_FIELDS, "access_token": token}
        return list(self._paginate(f"{self._base}/me/assigned_instagram_accounts", params))

    def exchange_code(self, code: str, redirect_uri: str) -> str:
        """연동 링크에서 돌아온 인가 코드를 시스템 사용자 토큰으로 바꾼다."""
        body = self._request(
            "GET",
            f"{self._base}/oauth/access_token",
            params={
                "client_id": self._app_id,
                "client_secret": self._app_secret,
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        return body["access_token"]

    def exchange_long_lived_user_token(self, user_token: str) -> str:
        """짧은 Facebook 사용자 토큰을 60일짜리로 바꾼다. 여기서 얻은 페이지 토큰은 만료되지 않는다."""
        body = self._request(
            "GET",
            f"{self._base}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": self._app_id,
                "client_secret": self._app_secret,
                "fb_exchange_token": user_token,
            },
        )
        return body["access_token"]

    def pages(self, user_token: str) -> list[dict]:
        """사용자가 관리하는 Facebook 페이지 목록. 각 항목에 페이지 토큰과 연결된 인스타 계정이 들어 있다."""
        params = {"fields": PAGE_FIELDS, "access_token": user_token}
        return list(self._paginate(f"{self._base}/me/accounts", params))

    def discover_account(self, token: str, ig_user_id: str, username: str) -> dict:
        """다른 공개 프로페셔널 계정의 프로필({"id", "username", "media_count"})을 조회한다."""
        _check_username(username)
        body = self._request(
            "GET",
            f"{self._base}/{ig_user_id}",
            params={
                "fields": f"business_discovery.username({username}){{id,username,media_count}}",
                "access_token": token,
            },
        )
        return body["business_discovery"]

    def iter_discovered_media(
        self, token: str, ig_user_id: str, username: str, page_size: int = 50
    ) -> Iterator[dict]:
        """Business Discovery로 다른 계정의 게시물을 최신순으로 끝까지 넘긴다.

        중첩 필드라 paging.next가 없고 cursors.after만 온다(2026-11-03 실제 응답 확인).
        커서를 media.after(...)에 넣어 다시 요청하고, 빈 페이지·커서 없음·같은 커서면 끝낸다.
        """
        _check_username(username)
        after = None
        while True:
            media = f"media.limit({page_size})" if after is None else f"media.after({after}).limit({page_size})"
            body = self._request(
                "GET",
                f"{self._base}/{ig_user_id}",
                params={
                    "fields": f"business_discovery.username({username}){{{media}{{{DISCOVERY_MEDIA_FIELDS}}}}}",
                    "access_token": token,
                },
            )
            page = body.get("business_discovery", {}).get("media", {})
            data = page.get("data", [])
            yield from data
            next_after = page.get("paging", {}).get("cursors", {}).get("after")
            if not data or not next_after or next_after == after:
                return
            after = next_after
            self._sleep(DISCOVERY_PAGE_DELAY)  # 남의 계정을 훑으므로 페이지 사이에 간격을 둔다.

    def _paginate(self, url: str | None, params: dict | None) -> Iterator[dict]:
        while url:
            body = self._request("GET", url, params=params)
            yield from body.get("data", [])
            # paging.next는 토큰·커서가 이미 들어 있는 완성된 URL이라 그대로 요청한다.
            url = body.get("paging", {}).get("next")
            params = None

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
