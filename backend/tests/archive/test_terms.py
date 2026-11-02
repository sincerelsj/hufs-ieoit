from datetime import date, datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.archive.terms import (
    TermOverlapError,
    check_no_overlap,
    delete_term,
    find_term,
    reassign_posts,
)
from app.models import Organization, Post, Term


def make_org(session: Session, slug: str = "dummy-council") -> Organization:
    org = Organization(
        slug=slug, name="더미 학생회", kind="student_council", department="더미학부"
    )
    session.add(org)
    session.flush()
    return org


def make_term(
    session: Session, org: Organization, start: date, end: date | None, name: str = "더미 임기"
) -> Term:
    term = Term(organization_id=org.id, name=name, start_date=start, end_date=end)
    session.add(term)
    session.flush()
    return term


def make_post(
    session: Session, org: Organization, key: str, posted_at: datetime, **kwargs
) -> Post:
    post = Post(
        organization_id=org.id,
        source="instagram_api",
        dedupe_key=key,
        posted_at=posted_at,
        academic_year=2026,
        media_type="IMAGE",
        **kwargs,
    )
    session.add(post)
    session.flush()
    return post


def test_overlap_rejected(session: Session):
    org = make_org(session)
    make_term(session, org, date(2025, 12, 1), date(2026, 11, 30))
    with pytest.raises(TermOverlapError):
        # 기존 임기의 마지막 날과 새 임기의 첫 날이 같다 (양끝 포함)
        check_no_overlap(session, org.id, date(2026, 11, 30), date(2027, 11, 30))


def test_adjacent_allowed(session: Session):
    org = make_org(session)
    make_term(session, org, date(2025, 12, 1), date(2026, 11, 30))
    check_no_overlap(session, org.id, date(2026, 12, 1), date(2027, 11, 30))


def test_open_ended_overlap(session: Session):
    org = make_org(session)
    make_term(session, org, date(2026, 12, 1), None)
    with pytest.raises(TermOverlapError):
        check_no_overlap(session, org.id, date(2030, 1, 1), None)


def test_new_open_ended_overlaps_later_term(session: Session):
    org = make_org(session)
    make_term(session, org, date(2027, 1, 1), date(2027, 12, 31))
    with pytest.raises(TermOverlapError):
        check_no_overlap(session, org.id, date(2026, 1, 1), None)


def test_other_org_does_not_overlap(session: Session):
    org_a = make_org(session, "dummy-a")
    org_b = make_org(session, "dummy-b")
    make_term(session, org_a, date(2025, 12, 1), None)
    check_no_overlap(session, org_b.id, date(2026, 1, 1), None)


def test_exclude_self_on_update(session: Session):
    org = make_org(session)
    term = make_term(session, org, date(2025, 12, 1), date(2026, 11, 30))
    with pytest.raises(TermOverlapError):
        check_no_overlap(session, org.id, date(2025, 12, 1), date(2026, 12, 31))
    check_no_overlap(
        session, org.id, date(2025, 12, 1), date(2026, 12, 31), exclude_term_id=term.id
    )


def test_end_before_start_rejected(session: Session):
    org = make_org(session)
    with pytest.raises(ValueError) as exc_info:
        check_no_overlap(session, org.id, date(2026, 5, 1), date(2026, 4, 30))
    assert not isinstance(exc_info.value, TermOverlapError)


def test_find_term_uses_kst(session: Session):
    org = make_org(session)
    term = make_term(session, org, date(2026, 3, 1), None)
    # 2026-02-28 15:30 UTC == 2026-03-01 00:30 KST
    posted_at = datetime(2026, 2, 28, 15, 30, tzinfo=timezone.utc)
    assert find_term(session, org.id, posted_at) == term
    # 1분 전(KST 2026-02-28 23:59)은 임기 밖
    assert find_term(session, org.id, datetime(2026, 2, 28, 14, 59, tzinfo=timezone.utc)) is None


def test_find_term_inclusive_end_and_open_end(session: Session):
    org = make_org(session)
    closed = make_term(session, org, date(2025, 12, 1), date(2026, 11, 30), "닫힌 임기")
    open_ = make_term(session, org, date(2026, 12, 1), None, "진행 중 임기")
    # KST 2026-11-30 23:59 == 2026-11-30 14:59 UTC -> 마지막 날 포함
    assert find_term(session, org.id, datetime(2026, 11, 30, 14, 59, tzinfo=timezone.utc)) == closed
    # KST 2026-12-01 00:00 == 2026-11-30 15:00 UTC
    assert find_term(session, org.id, datetime(2026, 11, 30, 15, 0, tzinfo=timezone.utc)) == open_
    assert find_term(session, org.id, datetime(2040, 1, 1, tzinfo=timezone.utc)) == open_


def test_reassign_skips_locked(session: Session):
    org = make_org(session)
    free = make_post(session, org, "ig:1", datetime(2026, 5, 1, tzinfo=timezone.utc))
    locked = make_post(
        session, org, "ig:2", datetime(2026, 5, 2, tzinfo=timezone.utc), term_locked=True
    )
    term = make_term(session, org, date(2026, 3, 1), None)

    assert reassign_posts(session, org.id) == 1
    assert free.term_id == term.id
    assert locked.term_id is None


def test_reassign_returns_zero_when_unchanged(session: Session):
    org = make_org(session)
    make_term(session, org, date(2026, 3, 1), None)
    make_post(session, org, "ig:1", datetime(2026, 5, 1, tzinfo=timezone.utc))
    assert reassign_posts(session, org.id) == 1
    assert reassign_posts(session, org.id) == 0


def test_reassign_only_touches_given_org(session: Session):
    org_a = make_org(session, "dummy-a")
    org_b = make_org(session, "dummy-b")
    make_term(session, org_a, date(2026, 3, 1), None)
    other = make_post(session, org_b, "ig:1", datetime(2026, 5, 1, tzinfo=timezone.utc))
    assert reassign_posts(session, org_a.id) == 0
    assert other.term_id is None


def test_reassign_after_delete_unassigns(session: Session):
    org = make_org(session)
    term = make_term(session, org, date(2026, 3, 1), None)
    post = make_post(session, org, "ig:1", datetime(2026, 5, 1, tzinfo=timezone.utc))
    assert reassign_posts(session, org.id) == 1
    assert post.term_id == term.id

    assert delete_term(session, term) == 0  # 이미 delete_term이 term_id를 비웠다
    assert post.term_id is None


def test_delete_term_leaves_other_terms_posts(session: Session):
    org = make_org(session)
    # 임기는 겹치지 않으므로 삭제된 임기의 게시물이 다른 임기로 옮겨 가지는 않는다.
    # 삭제된 쪽은 비워지고, 남은 임기의 게시물은 그대로여야 한다.
    kept = make_term(session, org, date(2026, 12, 1), None, "남는 임기")
    gone = make_term(session, org, date(2025, 12, 1), date(2026, 11, 30), "삭제될 임기")
    p_gone = make_post(session, org, "ig:1", datetime(2026, 5, 1, tzinfo=timezone.utc))
    p_kept = make_post(session, org, "ig:2", datetime(2027, 1, 1, tzinfo=timezone.utc))
    reassign_posts(session, org.id)
    assert (p_gone.term_id, p_kept.term_id) == (gone.id, kept.id)

    delete_term(session, gone)
    assert p_gone.term_id is None
    assert p_kept.term_id == kept.id


def test_delete_term_unlocks_locked_posts(session: Session):
    org = make_org(session)
    term = make_term(session, org, date(2026, 3, 1), None)
    locked = make_post(
        session,
        org,
        "ig:1",
        datetime(2026, 5, 1, tzinfo=timezone.utc),
        term_id=term.id,
        term_locked=True,
    )

    delete_term(session, term)

    assert locked.term_id is None
    assert locked.term_locked is False
