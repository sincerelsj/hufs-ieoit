from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.cli import main
from app.config import get_settings
from app.db import Base
from app.models import Channel, Organization
from app.security import decrypt_token, encrypt_token


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    db_path = tmp_path / "t.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("MEDIA_STORAGE", "local")
    monkeypatch.setenv("MEDIA_LOCAL_DIR", str(tmp_path / "media"))
    get_settings.cache_clear()
    yield db_path
    monkeypatch.undo()
    get_settings.cache_clear()


def test_sync_instagram_without_channels_prints_nothing(
    cli_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["sync-instagram"]) == 0
    assert capsys.readouterr().out == ""


@respx.mock
def test_sync_instagram_reports_channel_error(cli_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    settings = get_settings()
    engine = create_engine(f"sqlite:///{cli_db.as_posix()}")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            org = Organization(slug="test-org", name="테스트", kind="office", department="테스트학과")
            session.add(org)
            session.flush()
            session.add(
                Channel(
                    organization_id=org.id,
                    handle="dummy_account",
                    external_user_id="1",
                    access_token_enc=encrypt_token(settings, "T"),
                )
            )
            session.commit()
    finally:
        engine.dispose()
    respx.get(f"https://graph.facebook.com/{settings.instagram_api_version}/1/media").mock(
        return_value=httpx.Response(400, json={"error": {"code": 190, "message": "expired"}})
    )

    assert main(["sync-instagram", "--org", "test-org", "--full"]) == 1

    assert capsys.readouterr().out == "dummy_account: 새 0 · 갱신 0 · 미디어 실패 0 · 오류 needs_reauth\n"


def make_org(cli_db: Path, slug: str = "test-org") -> None:
    engine = create_engine(f"sqlite:///{cli_db.as_posix()}")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(Organization(slug=slug, name="테스트", kind="office", department="테스트학과"))
            session.commit()
    finally:
        engine.dispose()


def stored_channels(cli_db: Path) -> list[Channel]:
    engine = create_engine(f"sqlite:///{cli_db.as_posix()}")
    try:
        with Session(engine) as session:
            channels = session.query(Channel).order_by(Channel.id).all()
            session.expunge_all()
            return channels
    finally:
        engine.dispose()


def mock_accounts(accounts: list[dict]) -> respx.Route:
    settings = get_settings()
    return respx.get(
        f"https://graph.facebook.com/{settings.instagram_api_version}/me/assigned_instagram_accounts"
    ).mock(return_value=httpx.Response(200, json={"data": accounts}))


@pytest.fixture
def typed_token(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """getpass로 입력하는 토큰. 리스트에 넣은 값이 입력된다."""
    value = ["CONSOLE_TOKEN"]
    monkeypatch.setattr("app.cli.getpass.getpass", lambda prompt="": value[0])
    return value


@respx.mock
def test_register_instagram_connects_accounts_with_encrypted_token(
    cli_db: Path, typed_token: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    make_org(cli_db)
    route = mock_accounts([{"id": "17841400000000001", "username": "dummy_account"}])

    assert main(["register-instagram", "--org", "test-org"]) == 0

    assert route.calls[0].request.url.params["access_token"] == "CONSOLE_TOKEN"
    out = capsys.readouterr().out
    assert "test-org에 연결: @dummy_account" in out
    assert "CONSOLE_TOKEN" not in out
    [channel] = stored_channels(cli_db)
    assert channel.external_user_id == "17841400000000001"
    assert channel.handle == "dummy_account"
    assert channel.status == "active"
    assert channel.token_expires_at is None
    assert channel.access_token_enc != "CONSOLE_TOKEN"
    assert decrypt_token(get_settings(), channel.access_token_enc) == "CONSOLE_TOKEN"


@respx.mock
def test_register_instagram_account_option_picks_one(
    cli_db: Path, typed_token: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    make_org(cli_db)
    mock_accounts([
        {"id": "1", "username": "dummy_a"},
        {"id": "2", "username": "dummy_b"},
    ])

    assert main(["register-instagram", "--org", "test-org", "--account", "dummy_b"]) == 0

    assert [c.handle for c in stored_channels(cli_db)] == ["dummy_b"]


@respx.mock
def test_register_instagram_without_matching_account_fails(
    cli_db: Path, typed_token: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    make_org(cli_db)
    mock_accounts([{"id": "1", "username": "dummy_a"}])

    assert main(["register-instagram", "--org", "test-org", "--account", "nobody"]) == 1

    assert stored_channels(cli_db) == []


@respx.mock
def test_register_instagram_bad_token_fails_without_echoing_it(
    cli_db: Path, typed_token: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    make_org(cli_db)
    respx.get(url__regex=r"/me/assigned_instagram_accounts").mock(
        return_value=httpx.Response(400, json={"error": {"code": 190, "message": "Invalid OAuth access token"}})
    )

    assert main(["register-instagram", "--org", "test-org"]) == 1

    assert "CONSOLE_TOKEN" not in capsys.readouterr().out
    assert stored_channels(cli_db) == []


def test_register_instagram_unknown_org_fails(
    cli_db: Path, typed_token: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    make_org(cli_db)

    assert main(["register-instagram", "--org", "nope"]) == 1

    assert "nope" in capsys.readouterr().out


def test_register_instagram_empty_token_fails(
    cli_db: Path, typed_token: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    typed_token[0] = "   "

    assert main(["register-instagram", "--org", "test-org"]) == 1


@respx.mock
def test_register_instagram_account_of_other_org_conflicts(
    cli_db: Path, typed_token: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    make_org(cli_db, "org-a")
    make_org(cli_db, "org-b")
    mock_accounts([{"id": "1", "username": "dummy_account"}])
    assert main(["register-instagram", "--org", "org-a"]) == 0

    assert main(["register-instagram", "--org", "org-b"]) == 1

    [channel] = stored_channels(cli_db)
    assert channel.organization_id == 1
