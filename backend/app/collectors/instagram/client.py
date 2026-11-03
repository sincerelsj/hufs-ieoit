"""Instagram API(Unified login) 클라이언트. HTTP만 알고 DB는 모른다.

새 Meta 앱은 Instagram 로그인 방식을 쓸 수 없어 Unified login을 쓴다. 토큰은 비즈니스 포트폴리오에 묶인
시스템 사용자 토큰(만료 없음)이고, 모든 호출은 graph.facebook.com으로 간다.

보안: 액세스 토큰은 쿼리 파라미터로 전달되므로 요청 URL을 예외 메시지·로그에 넣지 않는다.
"""

import time
from collections.abc import Callable, Iterator

import httpx

MEDIA_FIELDS = (
    "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,username,"
    "children{id,media_type,media_url,thumbnail_url}"
)

ACCOUNT_FIELDS = "id,username"

GRAPH_HOST = "https://graph.facebook.com"

AUTH_ERROR_CODE = 190
RATE_LIMIT_ERROR_CODES = {4, 17, 32}


class InstagramError(Exception):
    pass


class InstagramAuthError(InstagramError):
    """토큰 만료·취소 (error.code == 190)."""


class InstagramRateLimitError(InstagramError):
    """HTTP 429 또는 error.code in {4, 17, 32}, 재시도 소진 후."""


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
