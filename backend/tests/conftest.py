from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (Base.metadata에 테이블 등록)
from app.config import Settings, get_settings
from app.db import Base, get_session, get_session_factory
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    # _env_file=None: 개발자의 실제 .env를 테스트가 읽지 않게 한다.
    return Settings(
        _env_file=None,
        token_encryption_key=Fernet.generate_key().decode(),
        state_secret="test-state-secret",
        admin_token="test-admin",
        instagram_app_id="test-app-id",
        instagram_app_secret="test-app-secret",
        instagram_redirect_uri="http://localhost:8000/integrations/instagram/callback",
        media_storage="local",
        media_local_dir=str(tmp_path / "media"),
    )


@pytest.fixture
def session() -> Iterator[Session]:
    # TestClient는 다른 스레드에서 돌므로 StaticPool + check_same_thread=False.
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


@pytest.fixture
def client(session: Session, settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_session] = lambda: session
    # 백그라운드 작업이 자기 Session을 열어도 같은 인메모리 DB를 쓰게 한다.
    app.dependency_overrides[get_session_factory] = lambda: sessionmaker(bind=session.get_bind())
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
