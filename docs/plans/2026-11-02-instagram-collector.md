# 인스타그램 수집기(B안) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 공식 Instagram API로 연동한 계정의 게시물을 조직·학년도·임기별로 저장하고 조회하는 FastAPI 백엔드를 만든다.

**Architecture:** `collectors/instagram`(HTTP·OAuth·동기화)이 API 응답을 정규화된 `PostIn`으로 바꿔 `archive/ingest`에 넘기고, `archive`가 학년도·임기 배정·중복 방지를 맡는다. 미디어 파일은 `MediaStorage`(로컬 / NCP Object Storage)에 복사한다. 관리 API는 `ADMIN_TOKEN` 헤더로 보호한다.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, pydantic-settings, httpx, cryptography(Fernet), itsdangerous, boto3, pytest, respx

**Spec:** [docs/specs/2026-11-02-instagram-collector-design.md](../specs/2026-11-02-instagram-collector-design.md)

## Global Constraints

- 모든 경로·명령은 `backend/` 기준. 테스트: `pytest -q` (backend 폴더에서).
- 학년도: KST 기준 3월 1일 ~ 이듬해 2월 말일. `academic_year(d) = d.year if d.month >= 3 else d.year - 1`.
- 시간은 DB에 UTC(aware)로 저장, 학년도·임기 계산 시 `Asia/Seoul`로 변환.
- Graph API 호스트 `https://graph.instagram.com/{INSTAGRAM_API_VERSION}` (기본 `v26.0`), 토큰 교환 `https://api.instagram.com/oauth/access_token`, 권한 `instagram_business_basic`.
- 인스타그램 타임스탬프 형식 `2026-11-01T08:14:43+0000` → `datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")`.
- `dedupe_key` 형식: `ig:<media_id>`. `(organization_id, dedupe_key)` unique.
- 비밀값은 환경변수로만. 새 변수는 `.env.example`에 이름만 추가.
- 테스트에서 실제 인스타그램 호출 금지(`respx`), 실제 게시물·개인정보 금지(더미 데이터만).
- 커밋 메시지 `<type>(be): <요약>`, 끝에 `Co-Authored-By` 줄.
- PR 1 = Task 1–6, PR 2 = Task 7–10, PR 3 = Task 11–12. 각 PR은 `feat/<이슈번호>-...` 브랜치.

## Review Focus

1. **캡션 없는 게시물** — API가 `caption` 키를 아예 안 줌 → `caption=None`으로 저장, 조회 API는 `null`. (Task 5, Task 10에 테스트)
2. **동기화 도중 토큰 만료(code 190)** — 이미 받은 페이지의 게시물은 커밋되고, 채널은 `needs_reauth`, 다른 채널은 계속. (Task 10)
3. **같은 인스타 계정을 다른 조직에 연결** — 409로 거부. **같은 조직에 같은 계정 재연결** — 채널 하나 유지, 토큰만 교체. (Task 11)
4. **하이픈 없는 휴대폰 번호**(`01012345678`)와 `010 1234 5678` — 공개 응답에서 마스킹. 학과 유선번호 `02-2173-3241`은 그대로. (Task 12)
5. **임기 밖 게시물** — 어떤 임기에도 안 걸리면 `unassigned`로 응답, 임기 삭제 시 그 게시물도 `unassigned`로 돌아감(고정 게시물 제외). (Task 4, Task 12)

---

## PR 1 — 뼈대·모델·저장 규칙

### Task 1: 백엔드 뼈대

**Files:**
- Create: `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/config.py`, `backend/app/db.py`, `backend/tests/conftest.py`, `backend/tests/test_health.py`
- Modify: `.env.example`, `backend/README.md` (세팅 명령을 `pip install -e ".[dev]"`로)

**Interfaces:**
- Produces:
  - `app.config.Settings` (pydantic-settings, `.env` 읽음) 필드: `database_url: str = "sqlite:///./local.db"`, `instagram_app_id: str = ""`, `instagram_app_secret: str = ""`, `instagram_redirect_uri: str = ""`, `instagram_api_version: str = "v26.0"`, `token_encryption_key: str = ""`, `state_secret: str = ""`, `admin_token: str = ""`, `media_storage: Literal["local","ncp"] = "local"`, `media_local_dir: str = "../data/raw/media"`, `ncp_object_storage_endpoint: str = "https://kr.object.ncloudstorage.com"`, `ncp_access_key`, `ncp_secret_key`, `ncp_bucket_name` (기본 `""`)
  - `app.config.get_settings() -> Settings` (lru_cache)
  - `app.db.Base` (DeclarativeBase), `app.db.make_engine(url: str) -> Engine`, `app.db.get_session()` FastAPI 의존성
  - `app.main.create_app(settings: Settings | None = None) -> FastAPI`, 모듈 전역 `app = create_app()`
  - 테스트 픽스처: `session`(SQLite 메모리 + `Base.metadata.create_all`), `client`(TestClient, `get_session` 오버라이드), `settings`(테스트용 키 채운 Settings)

- [ ] **Step 1: 실패하는 테스트** — `tests/test_health.py`

```python
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 2: 실행해 실패 확인** — `pytest tests/test_health.py -v` → FAIL (모듈 없음)
- [ ] **Step 3: 구현** — pyproject 의존성: `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2.0`, `pydantic-settings`, `httpx`, `cryptography`, `itsdangerous`, `boto3`; dev: `pytest`, `respx`. `create_app`에 `GET /health`. `.env.example`에 스펙 9장 변수 이름 추가(`INSTAGRAM_APP_ID` … `NCP_OBJECT_STORAGE_ENDPOINT`).
- [ ] **Step 4: 통과 확인** — `pytest -q` → 1 passed
- [ ] **Step 5: 커밋** — `chore(be): FastAPI 백엔드 뼈대와 설정 추가`

### Task 2: 학년도 계산

**Files:** Create `backend/app/archive/__init__.py`, `backend/app/archive/academic_year.py`, `backend/tests/archive/test_academic_year.py`

**Interfaces:**
- Produces: `KST = ZoneInfo("Asia/Seoul")`, `to_kst_date(dt: datetime) -> date` (naive 입력은 ValueError), `academic_year(dt: datetime) -> int`

- [ ] **Step 1: 실패하는 테스트**

```python
@pytest.mark.parametrize("utc, expected", [
    ("2026-02-28T14:59:59+00:00", 2025),  # KST 2/28 23:59:59
    ("2026-02-28T15:00:00+00:00", 2026),  # KST 3/1 00:00
    ("2028-02-29T03:00:00+00:00", 2027),  # 윤년
    ("2026-12-31T16:00:00+00:00", 2026),  # KST 2027-01-01
    ("2026-03-01T00:00:00+00:00", 2026),
])
def test_academic_year(utc, expected):
    assert academic_year(datetime.fromisoformat(utc)) == expected

def test_naive_rejected():
    with pytest.raises(ValueError):
        academic_year(datetime(2026, 3, 1))
```

- [ ] **Step 2: 실패 확인** — `pytest tests/archive/test_academic_year.py -v` → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: 커밋** — `feat(be): 학년도(3월~2월, KST) 계산 추가`

### Task 3: 데이터 모델

**Files:** Create `backend/app/models.py`, `backend/tests/test_models.py`

**Interfaces:**
- Produces (SQLAlchemy 2.0 `Mapped` 타입, 스펙 4장 컬럼 그대로):
  - `Organization(id, slug unique, name, kind: str, department, created_at)`; `kind` 값 `"student_council" | "office" | "club"`
  - `Term(id, organization_id FK, name, ordinal: int | None, start_date: date, end_date: date | None)`
  - `Channel(id, organization_id FK, platform="instagram", handle, external_user_id, access_token_enc: str | None, token_expires_at: datetime | None, status="active", last_synced_at: datetime | None)`, `UniqueConstraint(platform, external_user_id)`
  - `Post(id, organization_id FK, channel_id FK | None, source, dedupe_key, posted_at, academic_year: int, term_id FK | None, term_locked=False, caption: str | None, permalink: str | None, media_type, owner_username: str | None, raw_payload: JSON | None, created_at, updated_at)`, `UniqueConstraint(organization_id, dedupe_key)`
  - `PostMedia(id, post_id FK cascade delete, position, media_type, storage_key: str | None, thumbnail_key: str | None, source_url: str | None)`
  - 관계: `Organization.terms / channels / posts`, `Post.media`(position 순), `Post.term`

- [ ] **Step 1: 실패하는 테스트** — `test_post_dedupe_key_unique_per_org`(같은 org·같은 key 두 번 → `IntegrityError`, 다른 org는 허용), `test_channel_external_user_unique`(같은 `external_user_id` 두 채널 → `IntegrityError`), `test_post_media_ordered`(position 2,0,1로 넣고 `post.media` 순서가 0,1,2)
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: 커밋** — `feat(be): 조직·임기·채널·게시물 모델 추가`

### Task 4: 임기 규칙

**Files:** Create `backend/app/archive/terms.py`, `backend/tests/archive/test_terms.py`

**Interfaces:**
- Consumes: `to_kst_date` (Task 2), 모델 (Task 3)
- Produces:
  - `class TermOverlapError(ValueError)`
  - `check_no_overlap(session, organization_id: int, start: date, end: date | None, exclude_term_id: int | None = None) -> None` — 양끝 포함, `end=None`은 무한대
  - `find_term(session, organization_id: int, posted_at: datetime) -> Term | None`
  - `reassign_posts(session, organization_id: int) -> int` — `term_locked=False`인 게시물만 다시 배정, 바뀐 개수 반환

- [ ] **Step 1: 실패하는 테스트**
  - `test_overlap_rejected`: 2025-12-01~2026-11-30 있을 때 2026-11-30~2027-11-30 → `TermOverlapError` (양끝 포함)
  - `test_adjacent_allowed`: 2026-12-01~ → 통과
  - `test_open_ended_overlap`: 기존 end=None, 새 임기 2030-01-01~ → 에러
  - `test_exclude_self_on_update`
  - `test_find_term_uses_kst`: 임기 2026-03-01 시작, 게시 `2026-02-28T15:30:00Z` → 그 임기
  - `test_reassign_skips_locked`: 게시물 2개(하나 locked, term 없음) + 새 임기 → 반환 1, locked는 그대로
  - `test_reassign_after_delete_unassigns`: 임기 삭제 후 `reassign_posts` → 해당 게시물 `term_id is None` (Review Focus 5)
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: 커밋** — `feat(be): 임기 겹침 검사와 게시물 임기 배정 추가`

### Task 5: 공통 저장 입구 (`ingest`)

**Files:** Create `backend/app/archive/ingest.py`, `backend/tests/archive/test_ingest.py`

**Interfaces:**
- Consumes: `academic_year`, `find_term`, 모델
- Produces:

```python
@dataclass(frozen=True)
class MediaIn:
    position: int
    media_type: str            # "IMAGE" | "VIDEO"
    storage_key: str | None
    thumbnail_key: str | None = None
    source_url: str | None = None

@dataclass(frozen=True)
class PostIn:
    source: str                # "instagram_api" | "instagram_export" | "manual"
    dedupe_key: str
    posted_at: datetime        # aware
    media_type: str
    caption: str | None = None
    permalink: str | None = None
    owner_username: str | None = None
    raw_payload: dict | None = None
    media: tuple[MediaIn, ...] = ()

def upsert_post(session, organization_id: int, channel_id: int | None, post_in: PostIn) -> tuple[Post, bool]:
    """(post, created). 기존이면 caption·permalink·raw_payload 갱신, storage_key가 None인 미디어만 새 키로 채움."""
```

- [ ] **Step 1: 실패하는 테스트**
  - `test_create_sets_year_and_term`: 게시 `2026-10-30T10:31:00Z`, 임기 2026-03-01~ 있음 → `created is True`, `academic_year == 2026`, `term_id == 임기.id`
  - `test_second_upsert_updates_not_duplicates`: 같은 key, 캡션 변경 → `created is False`, 게시물 1개, 캡션 갱신
  - `test_upsert_keeps_locked_term`: locked 게시물 재upsert → term 유지
  - `test_media_retry_fills_missing_key`: 첫 upsert 미디어 `storage_key=None`, 두 번째 `"k1"` → 채워짐
  - `test_caption_missing`: `caption=None` 저장 (Review Focus 1)
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: 커밋** — `feat(be): 수집 공통 저장 입구(PostIn/upsert_post) 추가`

### Task 6: seed 명령

**Files:** Create `backend/app/cli.py`, `backend/tests/test_cli_seed.py`

**Interfaces:**
- Produces: `python -m app.cli seed` → `seed(session) -> int`(새로 만든 조직 수). 여러 번 실행해도 중복 없음. 임기는 만들지 않는다(기간은 운영자 확인 후 관리 API로 입력).

| slug | name | kind | department |
|---|---|---|---|
| `mecomm-council` | 미디어커뮤니케이션학부 학생회 | student_council | 미디어커뮤니케이션학부 |
| `mecomm-studio` | 미디어커뮤니케이션학부 방송제작실습실 | office | 미디어커뮤니케이션학부 |
| `mecomm-office` | 미디어커뮤니케이션학부 학부장실 | office | 미디어커뮤니케이션학부 |

- [ ] **Step 1: 실패하는 테스트** — `test_seed_idempotent`: `seed()` → 3, 다시 → 0, 조직 3개
- [ ] **Step 2–4: 실패 확인 → 구현(argparse 서브커맨드, 이후 Task에서 `sync-instagram`, `refresh-tokens` 추가) → 통과**
- [ ] **Step 5: 커밋** — `feat(be): 초기 조직 seed 명령 추가` → **PR 1 생성**

## PR 2 — 인스타 수집

### Task 7: Instagram API 클라이언트

**Files:** Create `backend/app/collectors/__init__.py`, `backend/app/collectors/instagram/__init__.py`, `backend/app/collectors/instagram/client.py`, `backend/tests/collectors/test_instagram_client.py`, `data/samples/instagram/media_page1.json`, `data/samples/instagram/media_page2.json` (더미 캡션·가짜 ID)

**Interfaces:**
- Produces:

```python
MEDIA_FIELDS = "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,username,children{id,media_type,media_url,thumbnail_url}"

class InstagramError(Exception): ...
class InstagramAuthError(InstagramError): ...       # error.code == 190
class InstagramRateLimitError(InstagramError): ...  # HTTP 429 또는 error.code in {4, 17, 32}, 재시도 소진 후

@dataclass(frozen=True)
class TokenInfo:
    access_token: str
    expires_at: datetime   # aware UTC

class InstagramClient:
    def __init__(self, http: httpx.Client, app_id: str, app_secret: str, api_version: str,
                 sleep: Callable[[float], None] = time.sleep, max_retries: int = 3): ...
    def iter_media(self, token: str, page_size: int = 50) -> Iterator[dict]: ...   # /me/media, paging.next 끝까지
    def me(self, token: str) -> dict: ...                                         # fields=user_id,username
    def exchange_code(self, code: str, redirect_uri: str) -> str: ...             # 단기 토큰
    def exchange_long_lived(self, short_token: str) -> TokenInfo: ...             # grant_type=ig_exchange_token
    def refresh(self, token: str) -> TokenInfo: ...                               # grant_type=ig_refresh_token
```

재시도: 지수 백오프 `sleep(2 ** attempt)`, `max_retries`회 후 `InstagramRateLimitError`.

- [ ] **Step 1: 실패하는 테스트** (`respx`)
  - `test_iter_media_follows_paging`: page1(`paging.next` 있음) + page2 → 항목 수 합계, 요청 2번
  - `test_iter_media_sends_fields`: 첫 요청 쿼리 `fields == MEDIA_FIELDS`, `limit == "50"`
  - `test_auth_error_190`: `{"error":{"code":190}}` 400 → `InstagramAuthError`
  - `test_rate_limit_retries_then_raises`: 429 ×4 → `InstagramRateLimitError`, `sleep` 호출 인자 `[1, 2, 4]`
  - `test_rate_limit_recovers`: 429 → 200 → 정상 반환
  - `test_exchange_long_lived_expiry`: `{"access_token":"L","expires_in":5184000}` → `expires_at ≈ now + 60일`
- [ ] **Step 2–4: 실패 확인 → 구현 → 통과**
- [ ] **Step 5: 커밋** — `feat(be): Instagram Graph API 클라이언트 추가`

### Task 8: 미디어 저장소

**Files:** Create `backend/app/storage.py`, `backend/tests/test_storage.py`

**Interfaces:**
- Produces:
  - `class MediaStorage(Protocol): def put(self, key: str, data: bytes, content_type: str) -> None; def open(self, key: str) -> bytes`
  - `LocalStorage(base_dir: Path)` — 키의 `..`·절대경로 거부(ValueError)
  - `NcpStorage(endpoint, access_key, secret_key, bucket)` — boto3 S3 클라이언트(`endpoint_url`), 테스트 제외
  - `make_storage(settings) -> MediaStorage`
  - `media_key(org_slug: str, media_id: str, ext: str) -> str` → `"instagram/<org_slug>/<media_id>.<ext>"`
- [ ] **Step 1: 실패하는 테스트** — `test_local_put_open_roundtrip`(tmp_path), `test_local_rejects_traversal`(`"../x"` → ValueError), `test_media_key_format`
- [ ] **Step 2–4: 실패 확인 → 구현 → 통과**
- [ ] **Step 5: 커밋** — `feat(be): 미디어 저장소(로컬/NCP) 추가`

### Task 9: 보안 유틸

**Files:** Create `backend/app/security.py`, `backend/tests/test_security.py`

**Interfaces:**
- Produces:
  - `encrypt_token(settings, token: str) -> str`, `decrypt_token(settings, enc: str) -> str` (Fernet, 키 = `TOKEN_ENCRYPTION_KEY`)
  - `sign_state(settings, org_slug: str) -> str`, `verify_state(settings, state: str, max_age: int = 600) -> str` (itsdangerous `URLSafeTimedSerializer`, 실패 시 `InvalidState(ValueError)`)
  - `require_admin` FastAPI 의존성: 헤더 `X-Admin-Token`을 `secrets.compare_digest`로 비교, 불일치·미설정 시 401
- [ ] **Step 1: 실패하는 테스트** — 암복호 왕복, 다른 키로 복호 실패, state 왕복, state 위조 → `InvalidState`, `max_age` 초과 → `InvalidState`(시간은 `freezegun` 없이 `max_age=-1`로), `ADMIN_TOKEN=""`이면 어떤 헤더든 401
- [ ] **Step 2–4: 실패 확인 → 구현 → 통과**
- [ ] **Step 5: 커밋** — `feat(be): 토큰 암호화·OAuth state·관리자 인증 추가`

### Task 10: 채널 동기화 + CLI

**Files:** Create `backend/app/collectors/instagram/sync.py`, `backend/tests/collectors/test_instagram_sync.py`; Modify `backend/app/cli.py`

**Interfaces:**
- Consumes: `InstagramClient`(Task 7), `MediaStorage`·`media_key`(Task 8), `decrypt_token`(Task 9), `PostIn`·`MediaIn`·`upsert_post`(Task 5)
- Produces:

```python
@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    media_failed: int = 0
    error: str | None = None   # "needs_reauth" | "rate_limited" | None

def to_post_in(item: dict, media: tuple[MediaIn, ...]) -> PostIn: ...
def sync_channel(session, channel: Channel, client: InstagramClient, storage: MediaStorage,
                 http: httpx.Client, settings: Settings, full: bool = False) -> SyncResult: ...
def sync_all(session, client, storage, http, settings, org_slug: str | None = None,
             full: bool = False) -> dict[str, SyncResult]: ...   # 키: channel.handle
```

규칙: 게시물마다 `session.commit()`(중간 실패해도 앞부분 보존). 증분 모드는 이미 있는 `dedupe_key`를 만나면 중단. 미디어: `CAROUSEL_ALBUM`은 `children` 순서대로, 각 항목 `media_url` → 실패/없음이면 `storage_key=None`(+`media_failed`), 동영상은 `thumbnail_url`도 받아 `thumbnail_key`. 확장자: IMAGE `jpg`, VIDEO `mp4`, 썸네일 `jpg`. `InstagramAuthError` → `channel.status="needs_reauth"`, `error="needs_reauth"`. 끝나면 `last_synced_at=now`.
CLI: `python -m app.cli sync-instagram [--org SLUG] [--full]` → 채널별 결과 한 줄씩 출력.

- [ ] **Step 1: 실패하는 테스트** (respx로 Graph API·CDN 모킹, `LocalStorage(tmp_path)`)
  - `test_to_post_in_parses_timestamp`: `"2026-11-01T08:14:43+0000"` → aware UTC, `dedupe_key == "ig:<id>"`, `caption` 키 없으면 None (Review Focus 1)
  - `test_full_sync_creates_posts_and_media`: 2페이지·캐러셀 1개(children 3) → `created == N`, 캐러셀 `PostMedia` 3개, 파일 존재
  - `test_incremental_stops_at_known`: 두 번째 실행 → 요청 1페이지만, `created == 0`
  - `test_media_download_failure_keeps_post`: CDN 403 → 게시물 저장, `media_failed == 1`, `storage_key is None`
  - `test_missing_media_url_uses_thumbnail`: VIDEO에 `media_url` 없음 → `thumbnail_key`만 채움
  - `test_auth_error_mid_pagination`: page1 정상, page2 code 190 → page1 게시물 커밋됨, 채널 `needs_reauth` (Review Focus 2)
  - `test_sync_all_continues_after_channel_failure`: 채널 A 190, 채널 B 정상 → B `created > 0`
- [ ] **Step 2–4: 실패 확인 → 구현 → 통과**
- [ ] **Step 5: 커밋** — `feat(be): 인스타 채널 동기화와 sync-instagram 명령 추가` → **PR 2 생성**

## PR 3 — 연결·조회·관리

### Task 11: OAuth 연결과 토큰 갱신

**Files:** Create `backend/app/collectors/instagram/oauth.py`, `backend/app/api/__init__.py`, `backend/app/api/integrations.py`, `backend/tests/collectors/test_instagram_oauth.py`; Modify `backend/app/main.py`, `backend/app/cli.py`

**Interfaces:**
- Consumes: `InstagramClient`, `TokenInfo`, `sign_state`/`verify_state`, `encrypt_token`/`decrypt_token`, `sync_channel`
- Produces:
  - `build_connect_url(settings, org_slug: str) -> str` — `https://www.instagram.com/oauth/authorize?client_id=…&redirect_uri=…&response_type=code&scope=instagram_business_basic&state=…`
  - `class ChannelConflict(Exception)`
  - `connect_channel(session, settings, org: Organization, token: TokenInfo, me: dict) -> Channel` — 같은 org·같은 `user_id`면 토큰·handle·status 갱신, 다른 org에 이미 있으면 `ChannelConflict`
  - `refresh_expiring(session, client, settings, now: datetime, within: timedelta = timedelta(days=10)) -> int`
  - 라우트 `GET /integrations/instagram/callback?code=&state=` → 성공 시 HTML "연동 완료" + `BackgroundTasks`로 `sync_channel(full=True)`; state 오류 400; 충돌 409
  - 의존성 `get_instagram_client()`, `get_storage()` (테스트에서 오버라이드)
  - CLI `refresh-tokens`
- [ ] **Step 1: 실패하는 테스트**
  - `test_connect_url_params`: 쿼리 `scope == "instagram_business_basic"`, `verify_state(state) == slug`
  - `test_callback_creates_channel`: 코드 교환·장기 토큰·`/me` 모킹 → 채널 1개, `access_token_enc != "L"`이고 복호 시 `"L"`
  - `test_reconnect_same_account_replaces_token`: 두 번 콜백 → 채널 1개, 새 토큰 (Review Focus 3)
  - `test_same_account_other_org_conflict`: → 409, 채널 1개 (Review Focus 3)
  - `test_bad_state_400`
  - `test_refresh_only_expiring`: 만료 5일 남은 채널·30일 남은 채널 → 반환 1, 앞 채널만 새 토큰
- [ ] **Step 2–4: 실패 확인 → 구현 → 통과**
- [ ] **Step 5: 커밋** — `feat(be): 인스타 OAuth 연결과 토큰 갱신 추가`

### Task 12: 조회·관리 API와 연락처 마스킹

**Files:** Create `backend/app/archive/masking.py`, `backend/app/api/archive.py`, `backend/app/api/admin.py`, `backend/app/api/schemas.py`, `backend/tests/api/test_archive_api.py`, `backend/tests/api/test_admin_api.py`, `backend/tests/archive/test_masking.py`; Modify `backend/app/main.py`, `docs/specs/2026-11-02-instagram-collector-design.md`(8장에 채널 삭제 API 한 줄 추가)

**Interfaces:**
- Consumes: 모델, `check_no_overlap`, `reassign_posts`, `build_connect_url`, `require_admin`, `MediaStorage.open`
- Produces:
  - `mask_phones(text: str | None) -> str | None` — 휴대폰 `01[016789]`로 시작하는 10–11자리(하이픈·공백 허용)를 `010-****-****` 형태로(앞 3자리 유지). `02-…` 등 유선번호는 유지
  - 공개: `GET /organizations` → `[{slug, name, kind, department}]`; `GET /organizations/{slug}/years` → `[{academic_year, count}]` 내림차순; `GET /organizations/{slug}/archive?academic_year=` → `{organization, academic_year, terms: [{id, name, start_date, end_date, posts: [...]}], unassigned: [...]}`, 게시물은 `posted_at` 내림차순, 캡션은 `mask_phones` 적용, 미디어는 `/media/{key}` URL; `GET /media/{key:path}` (local일 때만, 아니면 404)
  - 관리(`require_admin`): `POST /admin/organizations`; `POST /admin/organizations/{slug}/terms`, `PATCH /admin/organizations/{slug}/terms/{id}`, `DELETE …/terms/{id}` → 겹침 409, 변경 후 `reassign_posts`; `PATCH /admin/posts/{id}` `{term_id, term_locked}`; `GET /admin/organizations/{slug}/instagram/connect-url` → `{url}`; `DELETE /admin/channels/{id}?purge=true` → 채널 삭제, `purge`면 그 채널 게시물·미디어 파일도 삭제 (운영자 안내문의 "요청 시 기록 삭제" 약속)
- [ ] **Step 1: 실패하는 테스트**
  - `test_mask_phones`: `"010-1234-5678"`, `"01012345678"`, `"010 1234 5678"` → 마스킹, `"02-2173-3241"` 유지, `None` → `None` (Review Focus 4)
  - `test_archive_groups_by_term_and_unassigned`: 임기 1개 + 임기 밖 게시물 → `terms[0].posts` 1개, `unassigned` 1개 (Review Focus 5)
  - `test_archive_masks_caption`
  - `test_years_counts`: 2025·2026 게시물 → `[{2026, n}, {2025, m}]`
  - `test_admin_requires_token`: 헤더 없음 → 401
  - `test_create_term_overlap_409` / `test_create_term_reassigns`
  - `test_delete_channel_purge`: 게시물·`PostMedia`·저장 파일 삭제
- [ ] **Step 2–4: 실패 확인 → 구현 → 통과**
- [ ] **Step 5: 커밋** — `feat(be): 아카이브 조회·관리 API와 연락처 마스킹 추가` → **PR 3 생성**

## 실제 연동 후 수동 확인 (운영자 허가 이후)

1. Meta 앱 생성·테스터 초대 ([운영자 안내문](../guides/instagram-connect-guide.md)).
2. `connect-url`로 3개 계정 연결 → 콜백 후 전체 수집.
3. 확인: 게시물 수 = 프로필 표시 수, `caption` 존재(없으면 스펙 2장 재검토), 공동 게시물(@hufs_fbtk 글) 포함 여부, 학년도별 개수.
4. 결과를 `qa/scenarios/instagram-connect.md`에 기록.
