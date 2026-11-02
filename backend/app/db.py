from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


_session_factory: sessionmaker[Session] | None = None


def _get_session_factory() -> sessionmaker[Session]:
    # import 시점에 DB 파일이 만들어지지 않도록 처음 쓸 때 생성한다.
    global _session_factory
    if _session_factory is None:
        engine = make_engine(get_settings().database_url)
        _session_factory = sessionmaker(bind=engine)
    return _session_factory


def get_session() -> Iterator[Session]:
    with _get_session_factory()() as session:
        yield session
