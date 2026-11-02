"""Instagram 계정 연결(OAuth)과 장기 토큰 갱신.

보안: 토큰과 Graph API URL(토큰 포함)은 로그·예외 메시지에 남기지 않는다.
"""

from datetime import datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.instagram.client import InstagramAuthError, InstagramClient, InstagramError, TokenInfo
from app.config import Settings
from app.models import Channel, Organization
from app.security import TokenDecryptError, decrypt_token, encrypt_token, sign_state

AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
SCOPE = "instagram_business_basic"


class ChannelConflict(Exception):
    """이 Instagram 계정은 이미 다른 조직에 연결되어 있다."""


def build_connect_url(settings: Settings, org_slug: str) -> str:
    query = urlencode(
        {
            "client_id": settings.instagram_app_id,
            "redirect_uri": settings.instagram_redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "state": sign_state(settings, org_slug),
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def connect_channel(
    session: Session, settings: Settings, org: Organization, token: TokenInfo, me: dict
) -> Channel:
    """계정을 조직에 연결한다. flush만 하고 commit은 호출자가 한다."""
    external_user_id = str(me["user_id"])
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
    channel.handle = me["username"]
    channel.access_token_enc = encrypt_token(settings, token.access_token)
    channel.token_expires_at = token.expires_at
    channel.status = "active"
    session.flush()
    return channel


def refresh_expiring(
    session: Session,
    client: InstagramClient,
    settings: Settings,
    now: datetime,
    within: timedelta = timedelta(days=10),
) -> int:
    """만료가 `within` 이내인 활성 채널의 토큰을 갱신하고, 갱신한 채널 수를 돌려준다."""
    channels = session.scalars(
        select(Channel)
        .where(
            Channel.platform == "instagram",
            Channel.status == "active",
            Channel.access_token_enc.is_not(None),
            Channel.token_expires_at <= now + within,
        )
        .order_by(Channel.id)
    ).all()

    refreshed = 0
    for channel in channels:
        try:
            token = client.refresh(decrypt_token(settings, channel.access_token_enc))
        except InstagramAuthError:
            channel.status = "needs_reauth"
            continue
        except (InstagramError, TokenDecryptError):
            continue  # 이번 실행은 건너뛰고 다음 실행에서 다시 시도한다.
        channel.access_token_enc = encrypt_token(settings, token.access_token)
        channel.token_expires_at = token.expires_at
        refreshed += 1
    session.commit()
    return refreshed
