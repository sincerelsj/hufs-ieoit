"""관리 API. 모든 경로는 X-Admin-Token(require_admin)이 필요하다."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.archive import get_organization_or_404
from app.api.integrations import get_storage
from app.api.schemas import (
    ConnectUrlOut,
    OrganizationIn,
    OrganizationOut,
    PostOut,
    PostPatch,
    PurgeResult,
    TermIn,
    TermOut,
    TermPatch,
)
from app.archive.terms import TermOverlapError, check_no_overlap, delete_term, reassign_posts
from app.collectors.instagram.oauth import build_connect_url
from app.config import Settings, get_settings
from app.db import get_session
from app.models import Channel, Organization, Post, Term
from app.security import require_admin
from app.storage import MediaStorage

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


def _get_term_or_404(session: Session, org: Organization, term_id: int) -> Term:
    term = session.get(Term, term_id)
    if term is None or term.organization_id != org.id:
        raise HTTPException(404, "존재하지 않는 임기입니다.")
    return term


def _check_term_range(
    session: Session, org: Organization, term: TermIn, exclude_id: int | None = None
) -> None:
    try:
        check_no_overlap(session, org.id, term.start_date, term.end_date, exclude_term_id=exclude_id)
    except TermOverlapError as exc:  # ValueError의 하위 클래스라 먼저 잡는다.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/organizations", status_code=status.HTTP_201_CREATED, response_model=OrganizationOut)
def create_organization(
    body: OrganizationIn, session: Session = Depends(get_session)
) -> Organization:
    org = Organization(**body.model_dump())
    session.add(org)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 있는 slug입니다.") from None
    return org


@router.post(
    "/organizations/{slug}/terms", status_code=status.HTTP_201_CREATED, response_model=TermOut
)
def create_term(slug: str, body: TermIn, session: Session = Depends(get_session)) -> TermOut:
    org = get_organization_or_404(session, slug)
    _check_term_range(session, org, body)
    term = Term(organization_id=org.id, **body.model_dump())
    session.add(term)
    session.flush()
    reassigned = reassign_posts(session, org.id)
    session.commit()
    return TermOut.from_term(term, reassigned)


@router.patch("/organizations/{slug}/terms/{term_id}", response_model=TermOut)
def update_term(
    slug: str, term_id: int, body: TermPatch, session: Session = Depends(get_session)
) -> TermOut:
    org = get_organization_or_404(session, slug)
    term = _get_term_or_404(session, org, term_id)
    changes = body.model_dump(exclude_unset=True)
    # name, start_date는 비울 수 없으므로 null로 보내면 무시한다. ordinal, end_date는 null로 비울 수 있다.
    for required in ("name", "start_date"):
        if changes.get(required, True) is None:
            del changes[required]
    merged = TermIn(
        name=changes.get("name", term.name),
        ordinal=changes.get("ordinal", term.ordinal),
        start_date=changes.get("start_date", term.start_date),
        end_date=changes.get("end_date", term.end_date),
    )
    _check_term_range(session, org, merged, exclude_id=term.id)
    for field, value in merged.model_dump().items():
        setattr(term, field, value)
    session.flush()
    reassigned = reassign_posts(session, org.id)
    session.commit()
    return TermOut.from_term(term, reassigned)


@router.delete("/organizations/{slug}/terms/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_term(slug: str, term_id: int, session: Session = Depends(get_session)) -> Response:
    """204 No Content. 재배정된 게시물 개수는 돌려주지 않는다."""
    org = get_organization_or_404(session, slug)
    term = _get_term_or_404(session, org, term_id)
    delete_term(session, term)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/posts/{post_id}", response_model=PostOut)
def update_post(post_id: int, body: PostPatch, session: Session = Depends(get_session)) -> PostOut:
    post = session.get(Post, post_id)
    if post is None:
        raise HTTPException(404, "존재하지 않는 게시물입니다.")
    if body.term_id is not None:
        term = session.get(Term, body.term_id)
        if term is None or term.organization_id != post.organization_id:
            raise HTTPException(
                422, "term_id가 이 게시물 조직의 임기가 아닙니다."
            )
    post.term_id = body.term_id
    post.term_locked = body.term_locked
    session.commit()
    return PostOut.from_post(post)


@router.get("/organizations/{slug}/instagram/connect-url", response_model=ConnectUrlOut)
def connect_url(
    slug: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ConnectUrlOut:
    get_organization_or_404(session, slug)
    try:
        return ConnectUrlOut(url=build_connect_url(settings, slug))
    except RuntimeError:  # STATE_SECRET 미설정
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "서버 설정이 완료되지 않았습니다."
        ) from None


@router.delete("/channels/{channel_id}", response_model=PurgeResult)
def delete_channel(
    channel_id: int,
    purge: bool = False,
    session: Session = Depends(get_session),
    storage: MediaStorage = Depends(get_storage),
) -> PurgeResult:
    """채널 연결을 끊는다.

    purge=false(기본): 채널 행은 남기고 status="disconnected"로 바꾼 뒤 토큰을 지운다. 게시물은 그대로
    channel_id를 유지하므로 나중에 purge=true로 기록을 지울 수 있다.
    purge=true: 그 채널 게시물·미디어 파일·채널 행을 모두 지운다(운영자 요청 시 기록 삭제).
    """
    channel = session.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(404, "존재하지 않는 채널입니다.")
    if not purge:
        channel.status = "disconnected"
        channel.access_token_enc = None
        channel.token_expires_at = None
        session.commit()
        return PurgeResult(deleted_posts=0)
    posts = list(session.scalars(select(Post).where(Post.channel_id == channel.id)))
    # 파일을 먼저 지운다. 도중에 실패해도 DB는 그대로라 다시 시도할 수 있다(없는 키 삭제는 무시됨).
    for post in posts:
        for media in post.media:
            for key in (media.storage_key, media.thumbnail_key):
                if key:
                    storage.delete(key)
    for post in posts:
        session.delete(post)  # PostMedia는 cascade로 함께 삭제된다.
    session.flush()
    session.delete(channel)
    session.commit()
    return PurgeResult(deleted_posts=len(posts))
