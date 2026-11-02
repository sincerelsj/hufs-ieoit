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
from app.security import encrypt_token


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
    respx.get(f"https://graph.instagram.com/{settings.instagram_api_version}/me/media").mock(
        return_value=httpx.Response(400, json={"error": {"code": 190, "message": "expired"}})
    )

    assert main(["sync-instagram", "--org", "test-org", "--full"]) == 1

    assert capsys.readouterr().out == "dummy_account: 새 0 · 갱신 0 · 미디어 실패 0 · 오류 needs_reauth\n"
