"""공개 조회 API (인증 없음). 캡션의 연락처는 마스킹해서 내보낸다."""

import mimetypes
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.schemas import ArchiveOut, OrganizationOut, YearCount
from app.api.integrations import get_storage
from app.db import get_session
from app.models import Organization, Post, Term
from app.storage import MediaStorage

router = APIRouter()


def get_organization_or_404(session: Session, slug: str) -> Organization:
    org = session.scalar(select(Organization).where(Organization.slug == slug))
    if org is None:
        raise HTTPException(404, "존재하지 않는 조직입니다.")
    return org


@router.get("/organizations", response_model=list[OrganizationOut])
def list_organizations(session: Session = Depends(get_session)) -> list[Organization]:
    return list(session.scalars(select(Organization).order_by(Organization.slug)))


@router.get("/organizations/{slug}/years", response_model=list[YearCount])
def list_years(slug: str, session: Session = Depends(get_session)) -> list[YearCount]:
    org = get_organization_or_404(session, slug)
    rows = session.execute(
        select(Post.academic_year, func.count())
        .where(Post.organization_id == org.id)
        .group_by(Post.academic_year)
        .order_by(Post.academic_year.desc())
    )
    return [YearCount(academic_year=year, count=count) for year, count in rows]


@router.get("/organizations/{slug}/archive", response_model=ArchiveOut)
def get_archive(
    slug: str,
    academic_year: int = Query(ge=2000, le=2100),
    session: Session = Depends(get_session),
) -> ArchiveOut:
    org = get_organization_or_404(session, slug)
    window_start = date(academic_year, 3, 1)
    window_end = date(academic_year + 1, 3, 1) - timedelta(days=1)  # 이듬해 2월 말일

    posts = list(
        session.scalars(
            select(Post)
            .where(Post.organization_id == org.id, Post.academic_year == academic_year)
            .options(selectinload(Post.media))
            .order_by(Post.posted_at.desc(), Post.id.desc())
        )
    )
    by_term: dict[int | None, list[Post]] = {}
    for post in posts:
        by_term.setdefault(post.term_id, []).append(post)

    # 학년도 창과 겹치는 임기. 수동으로 고정한 게시물이 창 밖 임기를 가리켜도 사라지지 않도록
    # 그 해 게시물이 달린 임기도 함께 보여 준다.
    terms = session.scalars(
        select(Term)
        .where(
            Term.organization_id == org.id,
            or_(
                (Term.start_date <= window_end)
                & (Term.end_date.is_(None) | (Term.end_date >= window_start)),
                Term.id.in_([tid for tid in by_term if tid is not None]),
            ),
        )
        .order_by(Term.start_date, Term.id)
    )
    return ArchiveOut.build(
        org,
        academic_year,
        [(term, by_term.get(term.id, [])) for term in terms],
        by_term.get(None, []),
    )


@router.get("/media/{key:path}")
def get_media(key: str, storage: MediaStorage = Depends(get_storage)) -> Response:
    # 저장소 종류(local/ncp)와 상관없이 서버가 읽어서 내준다. 저장 키가 곧 공개 URL 경로다.
    try:
        data = storage.open(key)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404) from None
    content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    return Response(data, media_type=content_type, headers={"X-Content-Type-Options": "nosniff"})
