"""Business Discovery 수집 준비: 수집용 계정 토큰 저장과 수집 대상 계정 등록.

수집 대상 계정은 로그인·토큰 없이 username만 등록한다. 공개 비즈니스·크리에이터 계정이어야 한다.

보안: 토큰과 Graph API URL(토큰 포함)은 로그·예외 메시지에 남기지 않는다.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.instagram.client import InstagramClient
from app.collectors.instagram.oauth import ChannelConflict
from app.config import Settings
from app.models import Channel, CollectorCredential, Organization
from app.security import encrypt_token


class CollectorAccountNotFound(Exception):
    """토큰의 Facebook 페이지 중 인스타 계정이 연결된 페이지가 없다(또는 지정한 username이 없다)."""


class CollectorNotRegistered(Exception):
    """수집용 계정이 아직 등록되지 않았다(register-collector 먼저)."""


def register_collector(
    session: Session,
    settings: Settings,
    client: InstagramClient,
    user_token: str,
    username: str | None = None,
) -> CollectorCredential:
    """사용자 토큰을 60일 토큰 → 만료 없는 페이지 토큰으로 바꿔 저장한다. flush만 하고 commit은 호출자가 한다."""
    long_lived = client.exchange_long_lived_user_token(user_token)
    candidates = [
        page
        for page in client.pages(long_lived)
        if page.get("instagram_business_account") and page.get("access_token")
    ]
    if username:
        candidates = [p for p in candidates if p["instagram_business_account"].get("username") == username]
    if not candidates:
        raise CollectorAccountNotFound(
            "인스타 계정이 연결된 Facebook 페이지를 찾지 못했습니다. "
            "토큰을 받을 때 페이지와 인스타 계정을 선택했는지 확인하세요."
        )
    page = candidates[0]
    account = page["instagram_business_account"]

    credential = session.scalar(
        select(CollectorCredential).where(CollectorCredential.platform == "instagram")
    )
    if credential is None:
        credential = CollectorCredential(platform="instagram")
        session.add(credential)
    credential.ig_user_id = str(account["id"])
    credential.username = account["username"]
    credential.access_token_enc = encrypt_token(settings, page["access_token"])
    session.flush()
    return credential


def get_collector(session: Session) -> CollectorCredential:
    credential = session.scalar(
        select(CollectorCredential).where(CollectorCredential.platform == "instagram")
    )
    if credential is None:
        raise CollectorNotRegistered("수집용 계정이 없습니다. 먼저 register-collector를 실행하세요.")
    return credential


def add_discovery_channel(
    session: Session, org: Organization, account: dict
) -> Channel:
    """discover_account() 결과({"id", "username"})를 조직의 discovery 채널로 등록한다. commit은 호출자가 한다.

    같은 조직에 이미 있으면 discovery로 바꿔 다시 활성화한다. 다른 조직에 있으면 ChannelConflict.
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
    channel.collect_mode = "discovery"
    channel.access_token_enc = None
    channel.token_expires_at = None
    channel.status = "active"
    session.flush()
    return channel
