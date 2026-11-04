"""Instagram OAuth 콜백. 운영자가 동의 화면에서 돌아오는 곳이라 인증 헤더가 없고, 서명된 state로만 신뢰한다.

보안: 응답·로그에 토큰이나 Instagram URL을 싣지 않는다.
"""

import logging
from collections.abc import Iterator

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.collectors.instagram.client import InstagramClient, InstagramError
from app.collectors.instagram.oauth import ChannelConflict, connect_channel
from app.collectors.instagram.sync import sync_channel
from app.config import Settings, get_settings
from app.db import get_session, get_session_factory
from app.models import Channel, Organization
from app.security import InvalidState, verify_state
from app.storage import MediaStorage, make_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/instagram")


def get_http_client() -> Iterator[httpx.Client]:
    with httpx.Client(timeout=30) as http:
        yield http


def get_instagram_client(
    http: httpx.Client = Depends(get_http_client),
    settings: Settings = Depends(get_settings),
) -> InstagramClient:
    return InstagramClient(
        http,
        settings.instagram_app_id,
        settings.instagram_app_secret,
        settings.instagram_api_version,
    )


def get_storage(settings: Settings = Depends(get_settings)) -> MediaStorage:
    return make_storage(settings)


def run_initial_sync(
    session_factory: sessionmaker[Session],
    channel_id: int,
    settings: Settings,
    storage: MediaStorage | None = None,
) -> None:
    """연결 직후 전체 수집. 응답이 끝난 뒤 돌므로 요청의 Session·HTTP 클라이언트를 쓰지 않고 직접 연다."""
    try:
        with session_factory() as session, httpx.Client(timeout=30) as http:
            channel = session.get(Channel, channel_id)
            if channel is None:
                return
            client = InstagramClient(
                http,
                settings.instagram_app_id,
                settings.instagram_app_secret,
                settings.instagram_api_version,
            )
            sync_channel(
                session, channel, client, storage or make_storage(settings), http, settings, full=True
            )
    except Exception as exc:  # 백그라운드 작업이라 호출자에게 전파할 곳이 없다.
        # 예외 메시지에 URL(토큰 포함)이 있을 수 있어 종류만 남긴다.
        logger.error("초기 Instagram 수집 실패: %s", type(exc).__name__)


def _page(message: str, status_code: int = 200) -> HTMLResponse:
    html = (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Instagram 연동</title></head><body><p>{message}</p></body></html>"
    )
    return HTMLResponse(html, status_code=status_code)


@router.get("/callback", response_class=HTMLResponse)
def callback(
    background_tasks: BackgroundTasks,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_reason: str | None = Query(default=None),
    session: Session = Depends(get_session),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
    settings: Settings = Depends(get_settings),
    client: InstagramClient = Depends(get_instagram_client),
    storage: MediaStorage = Depends(get_storage),
) -> HTMLResponse:
    if error or error_reason:
        return _page("연동이 취소되었습니다. 필요하면 연결 링크로 다시 시도하세요.", 400)
    if not code or not state:
        return _page("잘못된 요청입니다. 연결 링크로 다시 시도하세요.", 400)
    try:
        slug = verify_state(settings, state, max_age=settings.oauth_state_max_age)
    except InvalidState:
        return _page("유효하지 않거나 만료된 연결 링크입니다. 새 연결 링크를 받아 다시 시도하세요.", 400)

    org = session.scalar(select(Organization).where(Organization.slug == slug))
    if org is None:
        return _page("존재하지 않는 조직입니다.", 404)

    # 인가 코드 끝에 `#_`가 붙어 오는 경우가 있다.
    code = code.removesuffix("#_")
    try:
        access_token = client.exchange_code(code, settings.instagram_redirect_uri)
        accounts = client.assigned_accounts(access_token)
    except (InstagramError, KeyError, ValueError):  # 응답 형식이 달라도 502로 정리한다.
        return _page("Instagram과 통신하지 못했습니다. 잠시 후 다시 시도하세요.", 502)
    if not accounts:
        return _page("공유된 Instagram 계정이 없습니다. 연결 링크로 다시 시도하면서 계정을 선택하세요.", 400)

    try:
        # 한 번에 여러 계정을 공유했다면 모두 이 조직에 연결한다.
        channel_ids = [
            connect_channel(session, settings, org, access_token, account).id for account in accounts
        ]
    except (ChannelConflict, KeyError):
        session.rollback()
        return _page("이 Instagram 계정은 이미 다른 조직에 연결되어 있습니다.", 409)
    session.commit()

    for channel_id in channel_ids:
        background_tasks.add_task(run_initial_sync, session_factory, channel_id, settings, storage)
    return _page("연동 완료. 게시물 수집을 시작했습니다. 이 창은 닫아도 됩니다.")
