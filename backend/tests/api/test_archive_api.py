from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.api.integrations import get_storage
from app.models import PostMedia
from app.storage import LocalStorage


def utc(y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


def test_list_organizations_ordered_by_slug(client, make_org):
    make_org("zeta", "제타")
    make_org("alpha", "알파", kind="club")
    r = client.get("/organizations")
    assert r.status_code == 200
    assert r.json() == [
        {"slug": "alpha", "name": "알파", "kind": "club", "department": "테스트학과"},
        {"slug": "zeta", "name": "제타", "kind": "student_council", "department": "테스트학과"},
    ]


def test_years_counts(client, make_org, make_post):
    org = make_org()
    make_post(org, utc(2025, 4, 1))
    make_post(org, utc(2026, 4, 1))
    make_post(org, utc(2026, 5, 1))
    other = make_org("other")
    make_post(other, utc(2026, 5, 1))
    r = client.get("/organizations/council/years")
    assert r.status_code == 200
    assert r.json() == [
        {"academic_year": 2026, "count": 2},
        {"academic_year": 2025, "count": 1},
    ]


def test_years_unknown_slug_404(client):
    assert client.get("/organizations/nope/years").status_code == 404


def test_archive_groups_by_term_and_unassigned(client, make_org, make_term, make_post):
    org = make_org()
    term = make_term(org, "제1대", date(2026, 3, 1), date(2026, 8, 31))
    make_post(org, utc(2026, 5, 1), term=term)
    make_post(org, utc(2026, 10, 1))  # 임기 밖
    r = client.get("/organizations/council/archive", params={"academic_year": 2026})
    assert r.status_code == 200
    body = r.json()
    assert body["organization"] == {
        "slug": "council", "name": "테스트 학생회", "kind": "student_council", "department": "테스트학과",
    }
    assert body["academic_year"] == 2026
    assert len(body["terms"]) == 1
    assert body["terms"][0]["name"] == "제1대"
    assert len(body["terms"][0]["posts"]) == 1
    assert len(body["unassigned"]) == 1


def test_archive_filters_terms_by_year_window_and_orders(client, make_org, make_term, make_post):
    org = make_org()
    make_term(org, "옛 임기", date(2024, 3, 1), date(2025, 2, 28))  # 2026학년도와 무관
    t2 = make_term(org, "제2대", date(2025, 3, 1), date(2026, 2, 28))  # 2025학년도만
    t3 = make_term(org, "제3대", date(2026, 3, 1), None)  # 진행 중
    make_post(org, utc(2026, 4, 1), term=t3)
    make_post(org, utc(2026, 6, 1), term=t3)
    make_post(org, utc(2025, 10, 1), term=t2)

    body = client.get("/organizations/council/archive", params={"academic_year": 2026}).json()
    assert [t["name"] for t in body["terms"]] == ["제3대"]
    posts = body["terms"][0]["posts"]
    assert [p["posted_at"] for p in posts] == sorted((p["posted_at"] for p in posts), reverse=True)
    assert len(posts) == 2

    body = client.get("/organizations/council/archive", params={"academic_year": 2025}).json()
    # 2026-02-28까지인 제2대는 2025학년도 창과 겹치고, 제3대는 2026-03-01 시작이라 겹치지 않는다.
    assert [t["name"] for t in body["terms"]] == ["제2대"]
    assert len(body["terms"][0]["posts"]) == 1


def test_archive_terms_ordered_by_start_date(client, make_org, make_term):
    org = make_org()
    make_term(org, "B", date(2026, 9, 1), None)
    make_term(org, "A", date(2026, 3, 1), date(2026, 8, 31))
    body = client.get("/organizations/council/archive", params={"academic_year": 2026}).json()
    assert [t["name"] for t in body["terms"]] == ["A", "B"]


def test_archive_requires_academic_year(client, make_org):
    make_org()
    assert client.get("/organizations/council/archive").status_code == 422


def test_archive_unknown_slug_404(client):
    r = client.get("/organizations/nope/archive", params={"academic_year": 2026})
    assert r.status_code == 404


def test_archive_masks_caption(client, make_org, make_post):
    org = make_org()
    make_post(org, utc(2026, 4, 1), caption="문의 010-1234-5678 사무실 02-2173-3241")
    body = client.get("/organizations/council/archive", params={"academic_year": 2026}).json()
    assert body["unassigned"][0]["caption"] == "문의 010-****-**** 사무실 02-2173-3241"


def test_archive_post_shape_hides_internal_fields(client, make_org, make_post):
    org = make_org()
    media = [
        PostMedia(position=0, media_type="IMAGE", storage_key="instagram/council/1.jpg",
                  thumbnail_key=None, source_url="https://cdn.example.invalid/x.jpg"),
        PostMedia(position=1, media_type="VIDEO", storage_key=None,
                  thumbnail_key="instagram/council/2_t.jpg", source_url=None),
    ]
    make_post(org, utc(2026, 4, 1), media=media)
    post = client.get("/organizations/council/archive", params={"academic_year": 2026}).json()["unassigned"][0]
    assert set(post) == {
        "id", "posted_at", "academic_year", "caption", "permalink", "media_type",
        "owner_username", "term_id", "term_locked", "media",
    }
    assert post["academic_year"] == 2026
    assert post["term_locked"] is False
    assert post["media"] == [
        {"position": 0, "media_type": "IMAGE", "url": "/media/instagram/council/1.jpg", "thumbnail_url": None},
        {"position": 1, "media_type": "VIDEO", "url": None, "thumbnail_url": "/media/instagram/council/2_t.jpg"},
    ]


def test_media_served_from_local_storage(client, settings):
    LocalStorage(Path(settings.media_local_dir)).put("instagram/c/a.jpg", b"JPEGDATA", "image/jpeg")
    r = client.get("/media/instagram/c/a.jpg")
    assert r.status_code == 200
    assert r.content == b"JPEGDATA"
    assert r.headers["content-type"] == "image/jpeg"


def test_media_unknown_extension_defaults_to_octet_stream(client, settings):
    LocalStorage(Path(settings.media_local_dir)).put("instagram/c/blob", b"x", "x")
    r = client.get("/media/instagram/c/blob")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"


def test_media_missing_or_invalid_key_404(client):
    assert client.get("/media/instagram/c/missing.jpg").status_code == 404
    assert client.get("/media/instagram/%5Cevil.jpg").status_code == 404


@pytest.mark.parametrize("year", [1999, 2101, 0, 99999999999])
def test_archive_academic_year_out_of_range_422(client, make_org, year):
    make_org()
    assert client.get(f"/organizations/council/archive?academic_year={year}").status_code == 422


def test_archive_academic_year_bounds_ok(client, make_org):
    make_org()
    assert client.get("/organizations/council/archive?academic_year=2000").status_code == 200
    assert client.get("/organizations/council/archive?academic_year=2100").status_code == 200


class _FakeNcpStorage:
    """NCP 저장소 대역. 실제 NCP를 호출하지 않는다."""

    def __init__(self, objects: dict[str, bytes]) -> None:
        self._objects = objects

    def open(self, key: str) -> bytes:
        try:
            return self._objects[key]
        except KeyError:
            raise FileNotFoundError(key) from None


def test_media_served_from_non_local_storage(client, settings):
    settings.media_storage = "ncp"
    client.app.dependency_overrides[get_storage] = lambda: _FakeNcpStorage(
        {"instagram/c/a.jpg": b"NCPDATA"}
    )
    r = client.get("/media/instagram/c/a.jpg")
    assert r.status_code == 200
    assert r.content == b"NCPDATA"
    assert r.headers["content-type"] == "image/jpeg"
    assert client.get("/media/instagram/c/missing.jpg").status_code == 404


def test_media_uses_make_storage_for_ncp_setting(client, settings, monkeypatch):
    settings.media_storage = "ncp"
    fake = _FakeNcpStorage({"instagram/c/b.png": b"PNG"})
    monkeypatch.setattr("app.api.integrations.make_storage", lambda s: fake)
    r = client.get("/media/instagram/c/b.png")
    assert r.status_code == 200
    assert r.content == b"PNG"
