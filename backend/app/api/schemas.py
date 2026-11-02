"""API 응답·요청 모델. raw_payload, 토큰, source_url 같은 내부 값은 응답에 싣지 않는다."""

from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict

from app.archive.masking import mask_phones
from app.models import Organization, Post, PostMedia, Term


def _media_url(key: str | None) -> str | None:
    return f"/media/{key}" if key else None


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    name: str
    kind: str
    department: str


class OrganizationIn(BaseModel):
    slug: str
    name: str
    kind: Literal["student_council", "office", "club"]
    department: str


class YearCount(BaseModel):
    academic_year: int
    count: int


class MediaOut(BaseModel):
    position: int
    media_type: str
    url: str | None
    thumbnail_url: str | None

    @classmethod
    def from_media(cls, media: PostMedia) -> Self:
        return cls(
            position=media.position,
            media_type=media.media_type,
            url=_media_url(media.storage_key),
            thumbnail_url=_media_url(media.thumbnail_key),
        )


class PostOut(BaseModel):
    id: int
    posted_at: datetime
    academic_year: int
    caption: str | None
    permalink: str | None
    media_type: str
    owner_username: str | None
    term_id: int | None
    term_locked: bool
    media: list[MediaOut]

    @classmethod
    def from_post(cls, post: Post) -> Self:
        return cls(
            id=post.id,
            posted_at=post.posted_at,
            academic_year=post.academic_year,
            caption=mask_phones(post.caption),
            permalink=post.permalink,
            media_type=post.media_type,
            owner_username=post.owner_username,
            term_id=post.term_id,
            term_locked=post.term_locked,
            media=[MediaOut.from_media(m) for m in post.media],
        )


class TermWithPosts(BaseModel):
    id: int
    name: str
    start_date: date
    end_date: date | None
    posts: list[PostOut]

    @classmethod
    def from_term(cls, term: Term, posts: list[Post]) -> Self:
        return cls(
            id=term.id,
            name=term.name,
            start_date=term.start_date,
            end_date=term.end_date,
            posts=[PostOut.from_post(p) for p in posts],
        )


class ArchiveOut(BaseModel):
    organization: OrganizationOut
    academic_year: int
    terms: list[TermWithPosts]
    unassigned: list[PostOut]

    @classmethod
    def build(
        cls,
        organization: Organization,
        academic_year: int,
        terms: list[tuple[Term, list[Post]]],
        unassigned: list[Post],
    ) -> Self:
        return cls(
            organization=OrganizationOut.model_validate(organization),
            academic_year=academic_year,
            terms=[TermWithPosts.from_term(t, posts) for t, posts in terms],
            unassigned=[PostOut.from_post(p) for p in unassigned],
        )


class TermIn(BaseModel):
    name: str
    ordinal: int | None = None
    start_date: date
    end_date: date | None = None


class TermPatch(BaseModel):
    """부분 수정. 보낸 필드만 바꾸므로 end_date를 null로 보내면 진행 중으로 되돌린다."""

    name: str | None = None
    ordinal: int | None = None
    start_date: date | None = None
    end_date: date | None = None


class TermOut(BaseModel):
    id: int
    name: str
    ordinal: int | None
    start_date: date
    end_date: date | None
    reassigned: int

    @classmethod
    def from_term(cls, term: Term, reassigned: int) -> Self:
        return cls(
            id=term.id,
            name=term.name,
            ordinal=term.ordinal,
            start_date=term.start_date,
            end_date=term.end_date,
            reassigned=reassigned,
        )


class PostPatch(BaseModel):
    term_id: int | None
    term_locked: bool


class ConnectUrlOut(BaseModel):
    url: str


class PurgeResult(BaseModel):
    deleted_posts: int
