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


# --- Business Discovery: register-collector / add-instagram ---------------

GRAPH = "https://graph.facebook.com/v26.0"


@pytest.fixture
def app_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSTAGRAM_APP_ID", "test-app-id")
    monkeypatch.setenv("INSTAGRAM_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("INSTAGRAM_API_VERSION", "v26.0")
    get_settings.cache_clear()


def mock_collector_pages() -> None:
    respx.get(f"{GRAPH}/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "LONG_USER_TOKEN"})
    )
    respx.get(f"{GRAPH}/me/accounts").mock(return_value=httpx.Response(200, json={"data": [{
        "id": "100", "name": "더미 페이지", "access_token": "PAGE_TOKEN",
        "instagram_business_account": {"id": "17841400000000001", "username": "dummy_collector"},
    }]}))


@respx.mock
def test_register_collector_saves_page_token(
    cli_db: Path, app_keys: None, typed_token: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    mock_collector_pages()

    assert main(["register-collector"]) == 0

    out = capsys.readouterr().out
    assert "@dummy_collector" in out
    assert "CONSOLE_TOKEN" not in out and "PAGE_TOKEN" not in out


def test_register_collector_requires_app_secret(
    cli_db: Path, typed_token: list[str], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("INSTAGRAM_APP_SECRET", "")
    get_settings.cache_clear()

    assert main(["register-collector"]) == 1

    assert "INSTAGRAM_APP_SECRET" in capsys.readouterr().out


@respx.mock
def test_add_instagram_registers_discovery_channel(
    cli_db: Path, app_keys: None, typed_token: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    make_org(cli_db)
    mock_collector_pages()
    assert main(["register-collector"]) == 0
    route = respx.get(f"{GRAPH}/17841400000000001").mock(return_value=httpx.Response(200, json={
        "business_discovery": {"id": "17841400000000009", "username": "dummy_target", "media_count": 12},
    }))

    assert main(["add-instagram", "--org", "test-org", "--username", "@dummy_target"]) == 0

    assert route.calls[0].request.url.params["access_token"] == "PAGE_TOKEN"
    assert "@dummy_target (게시물 12개)" in capsys.readouterr().out
    [channel] = stored_channels(cli_db)
    assert channel.collect_mode == "discovery"
    assert channel.handle == "dummy_target"
    assert channel.access_token_enc is None


def test_add_instagram_without_collector_fails(
    cli_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_org(cli_db)

    assert main(["add-instagram", "--org", "test-org", "--username", "dummy_target"]) == 1

    assert "register-collector" in capsys.readouterr().out


@respx.mock
def test_add_instagram_unknown_account_fails(
    cli_db: Path, app_keys: None, typed_token: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    make_org(cli_db)
    mock_collector_pages()
    assert main(["register-collector"]) == 0
    respx.get(f"{GRAPH}/17841400000000001").mock(return_value=httpx.Response(400, json={
        "error": {"code": 110, "error_subcode": 2207013, "message": "Invalid user id"},
    }))

    assert main(["add-instagram", "--org", "test-org", "--username", "dummy_private"]) == 1

    out = capsys.readouterr().out
    assert "공개 비즈니스·크리에이터 계정" in out
    assert "PAGE_TOKEN" not in out
    assert stored_channels(cli_db) == []
