import argparse
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, make_engine
from app.models import Organization  # 모델 모듈을 import해야 Base.metadata에 테이블이 등록된다.

SEED_ORGANIZATIONS: list[dict[str, str]] = [
    {
        "slug": "mecomm-council",
        "name": "미디어커뮤니케이션학부 학생회",
        "kind": "student_council",
        "department": "미디어커뮤니케이션학부",
    },
    {
        "slug": "mecomm-studio",
        "name": "미디어커뮤니케이션학부 방송제작실습실",
        "kind": "office",
        "department": "미디어커뮤니케이션학부",
    },
    {
        "slug": "mecomm-office",
        "name": "미디어커뮤니케이션학부 학부장실",
        "kind": "office",
        "department": "미디어커뮤니케이션학부",
    },
]


def seed(session: Session) -> int:
    """slug가 없는 조직만 추가하고, 새로 만든 조직 수를 돌려준다. commit은 호출자가 한다."""
    existing_slugs = set(session.scalars(select(Organization.slug)))
    added = 0
    for values in SEED_ORGANIZATIONS:
        if values["slug"] in existing_slugs:
            continue
        session.add(Organization(**values))
        added += 1
    session.flush()
    return added


def _cmd_seed(_args: argparse.Namespace) -> int:
    engine = make_engine(get_settings().database_url)
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            added = seed(session)
            session.commit()
    finally:
        engine.dispose()
    print(f"조직 {added}개 추가")
    return 0


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "seed": _cmd_seed,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="HUFS 이어:잇 백엔드 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed", help="초기 조직 데이터를 추가한다 (여러 번 실행해도 중복 없음)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
