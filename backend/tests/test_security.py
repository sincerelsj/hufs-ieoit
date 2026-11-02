import pytest
from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.security import (
    InvalidState,
    TokenDecryptError,
    decrypt_token,
    encrypt_token,
    require_admin,
    sign_state,
    verify_state,
)


def test_encrypt_decrypt_roundtrip(settings: Settings):
    enc = encrypt_token(settings, "dummy-access-token")
    assert enc != "dummy-access-token"
    assert decrypt_token(settings, enc) == "dummy-access-token"


def test_decrypt_with_other_key_fails(settings: Settings):
    enc = encrypt_token(settings, "dummy-access-token")
    other = settings.model_copy(update={"token_encryption_key": Fernet.generate_key().decode()})
    with pytest.raises(TokenDecryptError):
        decrypt_token(other, enc)


@pytest.mark.parametrize("key", ["", "not-a-valid-fernet-key"])
def test_encrypt_with_missing_or_invalid_key_raises_runtime_error(settings: Settings, key: str):
    bad = settings.model_copy(update={"token_encryption_key": key})
    with pytest.raises(RuntimeError, match="TOKEN_ENCRYPTION_KEY") as exc:
        encrypt_token(bad, "x")
    if key:
        assert key not in str(exc.value)


def test_state_roundtrip(settings: Settings):
    state = sign_state(settings, "student-council")
    assert verify_state(settings, state) == "student-council"


def test_state_tampered_raises_invalid_state(settings: Settings):
    state = sign_state(settings, "student-council")
    with pytest.raises(InvalidState):
        # 서명 끝 글자는 base64 패딩 비트라 바꿔도 디코딩 결과가 같을 수 있어 앞쪽(페이로드)을 바꾼다.
        verify_state(settings, ("A" if state[0] != "A" else "B") + state[1:])
    with pytest.raises(InvalidState):
        verify_state(settings, "garbage")


def test_state_signed_with_other_secret_raises_invalid_state(settings: Settings):
    state = sign_state(settings, "student-council")
    other = settings.model_copy(update={"state_secret": "another-secret"})
    with pytest.raises(InvalidState):
        verify_state(other, state)


def test_state_expired_raises_invalid_state(settings: Settings):
    state = sign_state(settings, "student-council")
    with pytest.raises(InvalidState):
        verify_state(settings, state, max_age=-1)


def test_state_empty_secret_refused(settings: Settings):
    state = sign_state(settings, "student-council")
    empty = settings.model_copy(update={"state_secret": ""})
    with pytest.raises(RuntimeError, match="STATE_SECRET"):
        sign_state(empty, "student-council")
    with pytest.raises(InvalidState):
        verify_state(empty, state)


def _admin_client(settings: Settings) -> TestClient:
    app = FastAPI()

    @app.get("/_t", dependencies=[Depends(require_admin)])
    def _t() -> dict[str, bool]:
        return {"ok": True}

    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_require_admin_correct_header(settings: Settings):
    r = _admin_client(settings).get("/_t", headers={"X-Admin-Token": "test-admin"})
    assert r.status_code == 200


def test_require_admin_wrong_header(settings: Settings):
    r = _admin_client(settings).get("/_t", headers={"X-Admin-Token": "nope"})
    assert r.status_code == 401


def test_require_admin_missing_header(settings: Settings):
    assert _admin_client(settings).get("/_t").status_code == 401


@pytest.mark.parametrize("header", ["", "anything", "test-admin"])
def test_require_admin_unset_token_always_401(settings: Settings, header: str):
    empty = settings.model_copy(update={"admin_token": ""})
    r = _admin_client(empty).get("/_t", headers={"X-Admin-Token": header})
    assert r.status_code == 401
