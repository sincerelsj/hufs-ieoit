from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.cli import main, seed
from app.config import get_settings
from app.models import Organization


def count_orgs(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Organization))


def test_seed_idempotent(session: Session) -> None:
    assert seed(session) == 3
    assert seed(session) == 0
    assert count_orgs(session) == 3


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    db_path = tmp_path / "t.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()
    yield db_path
    # 환경변수를 되돌린 뒤 설정 캐시를 비워야 다른 테스트가 이 DB를 보지 않는다.
    monkeypatch.undo()
    get_settings.cache_clear()


def test_cli_seed_creates_tables(cli_db: Path) -> None:
    assert main(["seed"]) == 0

    engine = create_engine(f"sqlite:///{cli_db.as_posix()}")
    try:
        with Session(engine) as session:
            assert count_orgs(session) == 3
    finally:
        engine.dispose()
