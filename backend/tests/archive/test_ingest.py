from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.archive.ingest import MediaIn, PostIn, upsert_post
from app.models import Channel, Organization, Post, PostMedia, Term

POSTED_AT = datetime(2026, 10, 30, 10, 31, tzinfo=timezone.utc)


def make_org(session: Session) -> Organization:
    org = Organization(
        slug="dummy-council", name="더미 학생회", kind="student_council", department="더미학부"
    )
    session.add(org)
    session.flush()
    return org


def make_term(session: Session, org: Organization, start: date, end: date | None = None) -> Term:
    term = Term(organization_id=org.id, name="더미 임기", start_date=start, end_date=end)
    session.add(term)
    session.flush()
    return term


def make_channel(session: Session, org: Organization) -> Channel:
    channel = Channel(organization_id=org.id, handle="dummy_handle", external_user_id="1000")
    session.add(channel)
    session.flush()
    return channel


def make_post_in(**kwargs) -> PostIn:
    defaults = dict(
        source="instagram_api",
        dedupe_key="ig:1",
        posted_at=POSTED_AT,
        media_type="IMAGE",
        caption="더미 캡션",
    )
    defaults.update(kwargs)
    return PostIn(**defaults)


def count_posts(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Post))


def test_create_sets_year_and_term(session: Session):
    org = make_org(session)
    term = make_term(session, org, date(2026, 3, 1))
    channel = make_channel(session, org)

    post, created = upsert_post(session, org.id, channel.id, make_post_in())

    assert created is True
    assert post.id is not None
    assert post.academic_year == 2026
    assert post.term_id == term.id
    assert post.term_locked is False
    assert post.channel_id == channel.id
    assert post.posted_at == POSTED_AT


def test_create_without_matching_term(session: Session):
    org = make_org(session)

    post, created = upsert_post(session, org.id, None, make_post_in())

    assert created is True
    assert post.term_id is None
    assert post.channel_id is None


def test_second_upsert_updates_not_duplicates(session: Session):
    org = make_org(session)
    first, _ = upsert_post(session, org.id, None, make_post_in(caption="처음"))

    second, created = upsert_post(
        session,
        org.id,
        None,
        make_post_in(caption="수정됨", permalink="https://example.test/p/1", raw_payload={"a": 1}),
    )

    assert created is False
    assert second.id == first.id
    assert count_posts(session) == 1
    assert second.caption == "수정됨"
    assert second.permalink == "https://example.test/p/1"
    assert second.raw_payload == {"a": 1}


def test_upsert_keeps_locked_term(session: Session):
    org = make_org(session)
    locked_term = make_term(session, org, date(2025, 3, 1), date(2026, 2, 28))
    make_term(session, org, date(2026, 3, 1))
    post, _ = upsert_post(session, org.id, None, make_post_in())
    post.term_id = locked_term.id
    post.term_locked = True
    session.flush()

    again, created = upsert_post(
        session,
        org.id,
        None,
        make_post_in(posted_at=datetime(2024, 1, 1, tzinfo=timezone.utc), caption="새 캡션"),
    )

    assert created is False
    assert again.term_id == locked_term.id
    assert again.term_locked is True
    assert again.posted_at == POSTED_AT
    assert again.academic_year == 2026
    assert again.caption == "새 캡션"


def test_media_retry_fills_missing_key(session: Session):
    org = make_org(session)
    post, _ = upsert_post(
        session,
        org.id,
        None,
        make_post_in(media=(MediaIn(position=0, media_type="IMAGE", storage_key=None),)),
    )
    assert [m.storage_key for m in post.media] == [None]

    post, created = upsert_post(
        session,
        org.id,
        None,
        make_post_in(
            media=(MediaIn(position=0, media_type="IMAGE", storage_key="k1", thumbnail_key="t1"),)
        ),
    )

    assert created is False
    assert len(post.media) == 1
    assert post.media[0].storage_key == "k1"
    assert post.media[0].thumbnail_key == "t1"


def test_media_never_overwrites_existing_key_or_deletes(session: Session):
    org = make_org(session)
    upsert_post(
        session,
        org.id,
        None,
        make_post_in(
            media=(
                MediaIn(position=0, media_type="IMAGE", storage_key="k0"),
                MediaIn(position=1, media_type="IMAGE", storage_key="k1"),
            )
        ),
    )

    post, _ = upsert_post(
        session,
        org.id,
        None,
        make_post_in(
            media=(
                MediaIn(position=0, media_type="IMAGE", storage_key="other"),
                MediaIn(position=2, media_type="VIDEO", storage_key="k2"),
            )
        ),
    )

    assert [(m.position, m.storage_key) for m in post.media] == [(0, "k0"), (1, "k1"), (2, "k2")]
    assert session.scalar(select(func.count()).select_from(PostMedia)) == 3


def test_caption_missing(session: Session):
    org = make_org(session)

    post, _ = upsert_post(session, org.id, None, make_post_in(caption=None))

    assert post.caption is None
    assert count_posts(session) == 1


def test_update_sets_channel_only_if_missing(session: Session):
    org = make_org(session)
    first_channel = make_channel(session, org)
    other_channel = Channel(organization_id=org.id, handle="other", external_user_id="2000")
    session.add(other_channel)
    session.flush()

    post, _ = upsert_post(session, org.id, None, make_post_in())
    post, _ = upsert_post(session, org.id, first_channel.id, make_post_in())
    assert post.channel_id == first_channel.id

    post, _ = upsert_post(session, org.id, other_channel.id, make_post_in())
    assert post.channel_id == first_channel.id
