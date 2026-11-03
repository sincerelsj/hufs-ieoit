import argparse
import getpass
import logging
from collections.abc import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.instagram.client import InstagramClient, InstagramError
from app.collectors.instagram.oauth import ChannelConflict, connect_channel
from app.collectors.instagram.sync import sync_all
from app.config import get_settings
from app.db import Base, make_engine
from app.models import Organization  # 모델 모듈을 import해야 Base.metadata에 테이블이 등록된다.
from app.storage import make_storage

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


def _cmd_sync_instagram(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session, httpx.Client(timeout=30) as http:
            client = InstagramClient(
                http,
                settings.instagram_app_id,
                settings.instagram_app_secret,
                settings.instagram_api_version,
            )
            results = sync_all(
                session, client, make_storage(settings), http, settings,
                org_slug=args.org, full=args.full,
            )
    finally:
        engine.dispose()

    for handle, result in results.items():
        line = f"{handle}: 새 {result.created} · 갱신 {result.updated} · 미디어 실패 {result.media_failed}"
        if result.error:
            line += f" · 오류 {result.error}"
        print(line)
    return 1 if any(r.error for r in results.values()) else 0


def _cmd_register_instagram(args: argparse.Namespace) -> int:
    """Meta 콘솔에서 발급한 토큰을 받아 조직에 연결한다. 토큰은 화면에 보이지 않게 입력받는다."""
    settings = get_settings()
    token = getpass.getpass("Meta 콘솔에서 복사한 액세스 토큰 (입력이 화면에 보이지 않습니다): ").strip()
    if not token:
        print("토큰이 비어 있습니다.")
        return 1

    engine = make_engine(settings.database_url)
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session, httpx.Client(timeout=30) as http:
            org = session.scalar(select(Organization).where(Organization.slug == args.org))
            if org is None:
                print(f"조직을 찾을 수 없습니다: {args.org} (먼저 seed를 실행하세요)")
                return 1
            client = InstagramClient(
                http,
                settings.instagram_app_id,
                settings.instagram_app_secret,
                settings.instagram_api_version,
            )
            try:
                accounts = client.assigned_accounts(token)
            except InstagramError as exc:
                print(f"토큰으로 계정을 조회하지 못했습니다: {exc}")
                return 1
            if args.account:
                accounts = [a for a in accounts if a.get("username") == args.account]
            if not accounts:
                print("이 토큰으로 접근할 수 있는 Instagram 계정이 없습니다(--account 이름도 확인하세요).")
                return 1
            try:
                for account in accounts:
                    connect_channel(session, settings, org, token, account)
            except ChannelConflict as exc:
                session.rollback()
                print(exc)
                return 1
            session.commit()
    finally:
        engine.dispose()

    handles = ", ".join(f"@{a['username']}" for a in accounts)
    print(f"{args.org}에 연결: {handles}")
    print(f"수집하려면: python -m app.cli sync-instagram --org {args.org} --full")
    return 0


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "seed": _cmd_seed,
    "sync-instagram": _cmd_sync_instagram,
    "register-instagram": _cmd_register_instagram,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="HUFS 이어:잇 백엔드 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed", help="초기 조직 데이터를 추가한다 (여러 번 실행해도 중복 없음)")
    sync = subparsers.add_parser("sync-instagram", help="연결된 Instagram 채널의 게시물을 수집한다")
    sync.add_argument("--org", help="이 조직 slug의 채널만 동기화한다")
    sync.add_argument("--full", action="store_true", help="끝까지 훑어 수정·실패한 미디어를 반영한다")
    register = subparsers.add_parser(
        "register-instagram", help="Meta 콘솔에서 발급한 Instagram 토큰을 조직에 연결한다"
    )
    register.add_argument("--org", required=True, help="연결할 조직 slug")
    register.add_argument("--account", help="토큰이 여러 계정에 접근할 때 이 username만 연결한다")
    return parser


def main(argv: list[str] | None = None) -> int:
    # httpx는 INFO 로그에 전체 URL(access_token 쿼리 포함)을 남기므로 WARNING 이상만 내보낸다.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
