"""보안 유틸: 토큰 암호화(Fernet), OAuth state 서명(itsdangerous), 관리자 인증 의존성."""

import secrets

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, Header, HTTPException, status
from itsdangerous import BadData, URLSafeTimedSerializer

from app.config import Settings, get_settings

_STATE_SALT = "instagram-oauth-state"


class TokenDecryptError(ValueError):
    """저장된 토큰을 복호화할 수 없음(키 불일치 또는 손상된 값)."""


class InvalidState(ValueError):
    """OAuth state 서명 불일치, 만료 또는 서명 비밀값 미설정."""


def _fernet(settings: Settings) -> Fernet:
    if not settings.token_encryption_key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY가 설정되지 않았습니다.")
    try:
        return Fernet(settings.token_encryption_key.encode())
    except (ValueError, TypeError):
        # 키 값 자체는 메시지에 넣지 않는다.
        raise RuntimeError("TOKEN_ENCRYPTION_KEY가 올바른 Fernet 키가 아닙니다.") from None


def encrypt_token(settings: Settings, token: str) -> str:
    return _fernet(settings).encrypt(token.encode()).decode()


def decrypt_token(settings: Settings, enc: str) -> str:
    try:
        return _fernet(settings).decrypt(enc.encode()).decode()
    except InvalidToken:
        raise TokenDecryptError("토큰을 복호화할 수 없습니다.") from None


def _state_serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.state_secret, salt=_STATE_SALT)


def sign_state(settings: Settings, org_slug: str) -> str:
    """빈 STATE_SECRET으로는 서명하지 않는다(RuntimeError)."""
    if not settings.state_secret:
        raise RuntimeError("STATE_SECRET이 설정되지 않았습니다.")
    return _state_serializer(settings).dumps(org_slug)


def verify_state(settings: Settings, state: str, max_age: int = 600) -> str:
    """서명·만료를 검증해 org slug를 돌려준다. 빈 STATE_SECRET이면 항상 InvalidState."""
    if not settings.state_secret:
        raise InvalidState("STATE_SECRET이 설정되지 않았습니다.")
    try:
        value = _state_serializer(settings).loads(state, max_age=max_age)
    except BadData:  # BadSignature, SignatureExpired 모두 포함
        raise InvalidState("유효하지 않거나 만료된 state입니다.") from None
    if not isinstance(value, str):
        raise InvalidState("유효하지 않은 state입니다.")
    return value


def require_admin(
    x_admin_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """X-Admin-Token 헤더가 ADMIN_TOKEN과 일치해야 한다. 미설정·불일치·누락이면 401."""
    if (
        not settings.admin_token
        or x_admin_token is None
        or not secrets.compare_digest(
            x_admin_token.encode(), settings.admin_token.encode()
        )
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "관리자 인증이 필요합니다.")
