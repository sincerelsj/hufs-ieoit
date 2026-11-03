"""Instagram 계정 연결. 연동 링크(Unified login)와 콘솔에서 발급한 토큰 등록이 같은 connect_channel을 쓴다.

토큰은 시스템 사용자 토큰이라 만료되지 않으므로 갱신 로직이 없다.

보안: 토큰과 Graph API URL(토큰 포함)은 로그·예외 메시지에 남기지 않는다.
"""

from urllib.parse import urlencode

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Channel, Organization
from app.security import encrypt_token, sign_state

AUTHORIZE_URL = "https://www.facebook.com/dialog/oauth"


class ChannelConflict(Exception):
    """이 Instagram 계정은 이미 다른 조직에 연결되어 있다."""


def missing_connect_settings(settings: Settings) -> list[str]:
    """연결 링크를 만들기 전에 필요한 설정 중 비었거나 잘못된 환경변수 이름을 돌려준다(값은 싣지 않는다)."""
    required = {
        "INSTAGRAM_APP_ID": settings.instagram_app_id,
        "INSTAGRAM_APP_SECRET": settings.instagram_app_secret,
        "INSTAGRAM_CONFIG_ID": settings.instagram_config_id,
        "INSTAGRAM_REDIRECT_URI": settings.instagram_redirect_uri,
        "STATE_SECRET": settings.state_secret,
        "TOKEN_ENCRYPTION_KEY": settings.token_encryption_key,
    }
    problems = [name for name, value in required.items() if not value]
    if settings.token_encryption_key:
        try:
            Fernet(settings.token_encryption_key.encode())
        except (ValueError, TypeError):
            problems.append("TOKEN_ENCRYPTION_KEY")
    return problems


def build_connect_url(settings: Settings, org_slug: str) -> str:
    query = urlencode(
        {
            "client_id": settings.instagram_app_id,
            "config_id": settings.instagram_config_id,
            "redirect_uri": settings.instagram_redirect_uri,
            "response_type": "code",
            "state": sign_state(settings, org_slug),
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def connect_channel(
    session: Session, settings: Settings, org: Organization, access_token: str, account: dict
) -> Channel:
    """계정을 조직에 연결한다. flush만 하고 commit은 호출자가 한다.

    account는 assigned_accounts()의 한 항목({"id", "username"})이다.

    같은 조직의 기존 채널은 상태(needs_reauth·disconnected 등)와 상관없이 다시 활성화한다.
    다른 조직에 연결된 계정은 상태와 상관없이 ChannelConflict.
    """
    external_user_id = str(account["id"])
    channel = session.scalar(
        select(Channel).where(
            Channel.platform == "instagram", Channel.external_user_id == external_user_id
        )
    )
    if channel is not None and channel.organization_id != org.id:
        raise ChannelConflict("이미 다른 조직에 연결된 Instagram 계정입니다.")
    if channel is None:
        channel = Channel(
            organization_id=org.id, platform="instagram", external_user_id=external_user_id
        )
        session.add(channel)
    channel.handle = account["username"]
    channel.access_token_enc = encrypt_token(settings, access_token)
    channel.token_expires_at = None
    channel.status = "active"
    session.flush()
    return channel

