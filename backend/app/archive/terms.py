from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.archive.academic_year import to_kst_date
from app.models import Post, Term


class TermOverlapError(ValueError):
    """같은 조직의 임기 기간이 겹칠 때 발생한다."""


def check_no_overlap(
    session: Session,
    organization_id: int,
    start: date,
    end: date | None,
    exclude_term_id: int | None = None,
) -> None:
    """[start, end] 가 같은 조직의 다른 임기와 겹치면 TermOverlapError. 양끝 포함, end=None은 무한대."""
    if end is not None and end < start:
        raise ValueError("임기 종료일은 시작일보다 빠를 수 없습니다")

    stmt = select(Term).where(Term.organization_id == organization_id)
    if exclude_term_id is not None:
        stmt = stmt.where(Term.id != exclude_term_id)

    for other in session.scalars(stmt):
        # 두 구간이 겹칠 조건: start <= other.end 이고 other.start <= end (None은 +무한대)
        starts_before_other_ends = other.end_date is None or start <= other.end_date
        other_starts_before_end = end is None or other.start_date <= end
        if starts_before_other_ends and other_starts_before_end:
            raise TermOverlapError(
                f"임기가 겹칩니다: {other.name} ({other.start_date} ~ {other.end_date or '진행 중'})"
            )


def _contains(term: Term, day: date) -> bool:
    return term.start_date <= day and (term.end_date is None or day <= term.end_date)


def find_term(session: Session, organization_id: int, posted_at: datetime) -> Term | None:
    """게시 시각(KST 날짜 기준)이 속하는 임기를 찾는다. 없으면 None."""
    day = to_kst_date(posted_at)
    terms = session.scalars(select(Term).where(Term.organization_id == organization_id))
    return next((t for t in terms if _contains(t, day)), None)


def reassign_posts(session: Session, organization_id: int) -> int:
    """term_locked=False인 게시물의 임기를 다시 배정하고 바뀐 개수를 돌려준다. flush만 하며 commit은 호출자 몫."""
    terms = list(session.scalars(select(Term).where(Term.organization_id == organization_id)))
    posts = session.scalars(
        select(Post).where(Post.organization_id == organization_id, Post.term_locked.is_(False))
    )
    changed = 0
    for post in posts:
        day = to_kst_date(post.posted_at)
        match = next((t for t in terms if _contains(t, day)), None)
        new_id = match.id if match else None
        if post.term_id != new_id:
            post.term_id = new_id
            changed += 1
    session.flush()
    return changed


def delete_term(session: Session, term: Term) -> int:
    """임기를 삭제한다. 이 임기를 가리키던 게시물은 잠금까지 풀고 나서 나머지를 재배정한다."""
    organization_id = term.organization_id
    for post in session.scalars(select(Post).where(Post.term_id == term.id)):
        post.term_id = None
        post.term_locked = False
    session.delete(term)
    session.flush()
    return reassign_posts(session, organization_id)
