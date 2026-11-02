from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Channel, Organization, Post, PostMedia, Term


def make_org(session: Session, slug: str = "dummy-council") -> Organization:
    org = Organization(
        slug=slug, name="더미 학생회", kind="student_council", department="더미학부"
    )
    session.add(org)
    session.flush()
    return org


def make_post(org: Organization, dedupe_key: str = "ig:1", **kwargs) -> Post:
    values = dict(
        organization_id=org.id,
        source="instagram_api",
        dedupe_key=dedupe_key,
        posted_at=datetime(2026, 11, 1, 8, 14, 43, tzinfo=timezone.utc),
        academic_year=2026,
        media_type="IMAGE",
    )
    values.update(kwargs)
    return Post(**values)


def test_post_dedupe_key_unique_per_org(session: Session):
    org_a = make_org(session, "dummy-a")
    org_b = make_org(session, "dummy-b")
    session.add(make_post(org_a))
    session.add(make_post(org_b))  # 다른 org는 같은 key 허용
    session.commit()

    session.add(make_post(org_a))
    with pytest.raises(IntegrityError):
        session.commit()


def test_channel_external_user_unique(session: Session):
    org = make_org(session)
    session.add(Channel(organization_id=org.id, handle="dummy_a", external_user_id="1001"))
    session.commit()

    session.add(Channel(organization_id=org.id, handle="dummy_b", external_user_id="1001"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_post_media_ordered(session: Session):
    org = make_org(session)
    post = make_post(org, media_type="CAROUSEL_ALBUM")
    for position in (2, 0, 1):
        post.media.append(PostMedia(position=position, media_type="IMAGE"))
    session.add(post)
    session.commit()
    session.expire_all()

    loaded = session.get(Post, post.id)
    assert [m.position for m in loaded.media] == [0, 1, 2]


def test_posted_at_roundtrips_as_aware_utc(session: Session):
    org = make_org(session)
    kst = timezone(timedelta(hours=9))
    post = make_post(org, posted_at=datetime(2026, 11, 1, 17, 14, 43, tzinfo=kst))
    session.add(post)
    session.commit()
    session.expire_all()

    loaded = session.get(Post, post.id)
    assert loaded.posted_at.tzinfo is not None
    assert loaded.posted_at == datetime(2026, 11, 1, 8, 14, 43, tzinfo=timezone.utc)
    assert loaded.posted_at.utcoffset() == timedelta(0)
    assert loaded.created_at.utcoffset() == timedelta(0)
    assert loaded.updated_at.utcoffset() == timedelta(0)


def test_naive_datetime_rejected(session: Session):
    org = make_org(session)
    session.add(make_post(org, posted_at=datetime(2026, 11, 1, 8, 0, 0)))
    with pytest.raises(Exception, match="timezone-aware"):
        session.commit()


def test_relationships_and_defaults(session: Session):
    org = make_org(session)
    term = Term(organization_id=org.id, name="제1대 더미", ordinal=1, start_date=date(2026, 3, 1))
    channel = Channel(organization_id=org.id, handle="dummy", external_user_id="2002")
    session.add_all([term, channel])
    session.flush()
    post = make_post(org, term_id=term.id, channel_id=channel.id)
    session.add(post)
    session.commit()
    session.expire_all()

    org = session.get(Organization, org.id)
    assert [t.name for t in org.terms] == ["제1대 더미"]
    assert [c.platform for c in org.channels] == ["instagram"]
    assert [c.status for c in org.channels] == ["active"]
    assert len(org.posts) == 1
    assert org.posts[0].term.id == term.id
    assert org.posts[0].channel.id == channel.id
    assert org.posts[0].term_locked is False
    assert org.created_at.tzinfo is not None
