from collections.abc import Callable
from datetime import date, datetime

import pytest
from sqlalchemy.orm import Session

from app.archive.academic_year import academic_year
from app.models import Channel, Organization, Post, PostMedia, Term

ADMIN = {"X-Admin-Token": "test-admin"}


@pytest.fixture
def admin() -> dict[str, str]:
    return ADMIN


@pytest.fixture
def make_org(session: Session) -> Callable[..., Organization]:
    def _make(slug: str = "council", name: str = "테스트 학생회", kind: str = "student_council") -> Organization:
        org = Organization(slug=slug, name=name, kind=kind, department="테스트학과")
        session.add(org)
        session.commit()
        return org

    return _make


@pytest.fixture
def make_term(session: Session) -> Callable[..., Term]:
    def _make(
        org: Organization,
        name: str = "제1대",
        start: date = date(2026, 3, 1),
        end: date | None = date(2027, 2, 28),
    ) -> Term:
        term = Term(organization_id=org.id, name=name, start_date=start, end_date=end)
        session.add(term)
        session.commit()
        return term

    return _make


@pytest.fixture
def make_post(session: Session) -> Callable[..., Post]:
    counter = iter(range(1, 10_000))

    def _make(
        org: Organization,
        posted_at: datetime,
        term: Term | None = None,
        caption: str | None = "더미 캡션",
        channel: Channel | None = None,
        media: list[PostMedia] | None = None,
    ) -> Post:
        n = next(counter)
        post = Post(
            organization_id=org.id,
            channel_id=channel.id if channel else None,
            source="instagram",
            dedupe_key=f"ig:{n}",
            posted_at=posted_at,
            academic_year=academic_year(posted_at),
            term_id=term.id if term else None,
            caption=caption,
            permalink=f"https://example.invalid/p/{n}",
            media_type="IMAGE",
            owner_username="dummy_user",
            raw_payload={"secret": "raw"},
            media=media or [],
        )
        session.add(post)
        session.commit()
        return post

    return _make

