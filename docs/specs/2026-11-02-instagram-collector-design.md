# 인스타그램 수집기 + 조직·연도 아카이브 설계

- 날짜: 2026-11-02
- 상태: 검토 중
- 담당 영역: BE (`backend/`)

## 1. 목표

학생회·학과 사무실 인스타그램 게시물을 **공식 API로** 모아, **조직별 · 학년도별 · 임기별**로 조회할 수 있게 한다.

첫 대상 계정 3개:

| 계정 | 조직 | 유형 |
|---|---|---|
| [@hufs_mecomm](https://www.instagram.com/hufs_mecomm/) | 미디어커뮤니케이션학부 학생회 (현재 제38대 '은하') | 학생회 |
| [@hufsmecomm_studio](https://www.instagram.com/hufsmecomm_studio/) | 미디어커뮤니케이션학부 방송제작실습실 | 학과사무실 |
| [@hufscommu_office](https://www.instagram.com/hufscommu_office/) | 미디어커뮤니케이션학부 학부장실 | 학과사무실 |

성공 기준:
- 운영자가 연결 링크로 한 번 로그인하면, 해당 계정의 과거 게시물 전체가 캡션·게시일·이미지와 함께 저장된다.
- 이후 동기화 명령을 돌리면 새 게시물만 추가된다.
- `GET /organizations/{slug}/archive?academic_year=2026`이 임기별로 묶인 게시물을 돌려준다.
- 학생회 기수가 바뀌어도 같은 계정의 수집이 끊기지 않고, 게시물은 게시일에 맞는 기수로 배정된다.

## 2. 수집 방식 결정

| 방식 | 결정 |
|---|---|
| **B. 공식 Instagram API (Instagram 로그인)** | **이번 범위.** 운영자 동의 기반, 지속 자동 수집 |
| A. 운영자의 "내 정보 다운로드" 파일 가져오기 | 후속. 같은 저장 경로(`ingest`)를 쓰도록 인터페이스만 맞춰 둔다 |
| C. 비공식 스크래핑 | **사용하지 않음.** 이용약관 위반·계정 정지 위험, 공개 레포·심사 리스크 |

API 전제 (Meta 문서 기준):
- 대상 계정은 **프로페셔널 계정**(크리에이터/비즈니스)이어야 한다. Facebook 페이지 연결은 불필요.
- 권한: `instagram_business_basic` (자기 계정 게시물 읽기만).
- 앱은 개발 모드로 운영하고, 3개 계정을 **Instagram 테스터**로 등록한다 → App Review 없이 사용 가능. 다른 학과로 확대할 때 App Review 진행.
- 호스트: `graph.instagram.com`, 버전은 환경변수(`INSTAGRAM_API_VERSION`, 기본 `v26.0`)로 둔다.

API로 **못 가져오는 것**: 하이라이트, 지난 스토리, 다른 사람 계정. → A 방식 또는 직접 등록으로 보완.

> ⚠️ 첫 토큰 발급 직후 확인: `caption` 필드가 Instagram 로그인 경로에서 내려오는지. 안 내려오면 이 설계의 수집 방식을 재검토한다.

### 2.1 과거 기록 범위 (예: 2018년~현재)

| 방법 | 가져올 수 있는 범위 |
|---|---|
| 로그아웃 공개 화면 (2026-11-02 샘플) | 계정당 최근 **약 12개**뿐. 과거 아카이빙 불가 |
| B. 공식 API `/me/media` | 그 계정에 **현재 남아 있는 피드 게시물 전체** (페이지를 끝까지 넘김). 상한 여부는 첫 연동 때 게시물 수와 대조해 확인 |
| A. 내보내기 파일 | 계정 개설 이후 전체 + 지난 스토리·하이라이트 일부 |

- 삭제·보관(archive)된 게시물은 B로 못 가져온다 (A는 보관 게시물 포함).
- 계정이 생기기 전 기록, 또는 **예전 학생회가 다른 계정을 썼다면** 그 계정도 따로 연결(B)하거나 내보내기(A)해야 한다. 한 조직에 채널 여러 개를 붙일 수 있게 한다(4장 `channels`는 이미 1:N).

### 2.2 샘플에서 확인한 점 (2026-11-02, 3개 계정 34개 게시물)

- **개인 연락처가 캡션에 있다** (학생회장·조교 휴대폰 번호). 공개 화면에 보여 줄 때 `010-XXXX-XXXX` 형태는 마스킹하고, 원문은 권한 있는 사용자만 본다.
- **같은 내용을 여러 번 올린 게시물**이 있다 (학생회 3건씩 2묶음). ID가 달라 중복 제거 대상은 아니지만, 화면에서 묶어 보이는 처리는 후속 과제.
- **공동 게시물(collab)**: 다른 계정(@hufs_fbtk)이 올리고 학생회가 공동 작성자로 들어간 글이 학생회 피드에 보인다. `owner_username`을 저장하고, API가 공동 게시물을 돌려주는지 첫 연동 때 확인.
- 학부장실·실습실 공지는 "**자세한 내용은 카드뉴스 참고**"가 많다 → 핵심 정보가 이미지 안에 있다. 이미지 OCR(CLOVA OCR)은 AI 단계 후속 과제로 둔다.
- 실습실 공지의 문의 번호가 학기마다 바뀐다 → 조교 교체가 실제로 일어나고 있고, 임기(Term)를 사무실에도 둘 필요가 확인됨.

## 3. 핵심 규칙

### 3.1 학년도
- 학년도 = **3월 1일 ~ 이듬해 2월 말일**. 게시일을 **KST**로 바꾼 뒤 계산한다.
- `academic_year(d) = d.year if d.month >= 3 else d.year - 1`
  - 2026-02-28 23:59 KST → 2025학년도, 2026-03-01 00:00 KST → 2026학년도
- 저장 시 `posts.academic_year` 컬럼에 계산해 넣는다 (조회·인덱스용).

### 3.2 임기(Term)
- 학년도와 **별개로** 조직마다 임기를 둔다. 학생회는 기수(제38대 '은하'), 사무실은 담당 조교 교체 단위(없어도 됨).
- 임기 = `시작일 ~ 종료일`(KST 날짜, 양끝 포함). 종료일이 비어 있으면 현재 진행 중.
- 같은 조직의 임기는 **겹칠 수 없다** (생성·수정 시 거부).
- 게시물 배정: 게시일(KST 날짜)이 들어가는 임기. 없으면 `term_id = NULL` → 화면에서 "임기 미지정"으로 표시.
- 임기를 추가·수정·삭제하면 그 조직의 게시물을 다시 배정한다. 단, 관리자가 수동으로 고정한 게시물(`term_locked = true`)은 건드리지 않는다.

### 3.3 계정은 조직에 붙는다
인스타 계정(채널)과 토큰은 **임기가 아니라 조직**에 연결한다. 기수가 바뀌어 운영자가 달라져도 수집은 계속되고, 새 운영자가 다시 로그인하면 토큰만 교체된다.

## 4. 데이터 모델

```
Organization 1─* Term
Organization 1─* Channel
Organization 1─* Post *─0..1 Term
Post 1─* PostMedia
```

**organizations**
| 컬럼 | 설명 |
|---|---|
| id, slug (unique) | 예: `mecomm-council`, `mecomm-studio`, `mecomm-office` |
| name | 미디어커뮤니케이션학부 학생회 |
| kind | `student_council` \| `office` \| `club` |
| department | 미디어커뮤니케이션학부 |

**terms**
| 컬럼 | 설명 |
|---|---|
| id, organization_id | |
| name | 제38대 학생회 '은하' |
| ordinal | 38 (학생회 기수, 없으면 NULL) |
| start_date, end_date | KST 날짜, end_date NULL = 진행 중 |

**channels**
| 컬럼 | 설명 |
|---|---|
| id, organization_id | |
| platform | `instagram` |
| handle | hufs_mecomm |
| external_user_id | 인스타 사용자 ID, (platform, external_user_id) unique |
| access_token_enc | Fernet 암호화한 장기 토큰 |
| token_expires_at | |
| status | `active` \| `needs_reauth` \| `disconnected` |
| last_synced_at | |

**posts**
| 컬럼 | 설명 |
|---|---|
| id, organization_id, channel_id (NULL 가능) | |
| source | `instagram_api` \| `instagram_export` \| `manual` |
| dedupe_key | (organization_id, dedupe_key) unique. API: `ig:<media_id>` |
| posted_at | UTC 저장 |
| academic_year | 3.1 규칙으로 계산 |
| term_id, term_locked | 3.2 규칙 |
| caption, permalink, media_type | `IMAGE` \| `VIDEO` \| `CAROUSEL_ALBUM` |
| owner_username | 게시한 계정 (공동 게시물이면 채널 핸들과 다를 수 있음) |
| raw_payload | API 원본 JSON (나중에 AI 분류·재처리용) |

**post_media**
| 컬럼 | 설명 |
|---|---|
| id, post_id, position | 캐러셀 순서 |
| media_type | `IMAGE` \| `VIDEO` |
| storage_key | 우리 저장소 경로 (`instagram/<org>/<media_id>.jpg`) |
| thumbnail_key | 동영상 썸네일 |

구성원(Membership)은 **이번 범위 밖**이다. 설계 방향만 7장에 남긴다.

## 5. 구성 요소

```
backend/
├── app/
│   ├── main.py                 FastAPI 앱, 라우터 등록
│   ├── config.py               환경변수 (pydantic-settings)
│   ├── db.py                   SQLAlchemy 엔진·세션, create_all
│   ├── models.py               4장 테이블
│   ├── archive/
│   │   ├── academic_year.py    academic_year(), KST 변환
│   │   ├── terms.py            임기 겹침 검사, 게시물 임기 배정·재배정
│   │   └── ingest.py           PostIn(정규화 형식) → upsert. A·B·직접 등록 공통 입구
│   ├── collectors/instagram/
│   │   ├── client.py           Graph API 호출 (미디어 목록·캐러셀·토큰 교환/갱신)
│   │   ├── oauth.py            연결 URL 생성, 콜백 처리
│   │   └── sync.py             채널 하나 동기화
│   ├── storage.py              MediaStorage: Local / NCP Object Storage(S3 호환)
│   ├── security.py             토큰 암호화, OAuth state 서명, 관리자 토큰 검사
│   ├── api/                    archive.py(조회), admin.py(관리)
│   └── cli.py                  seed / sync-instagram / refresh-tokens
└── tests/
```

각 단위의 경계:
- `client.py`는 HTTP만 안다 (DB 모름). 테스트에서 `respx`로 응답을 흉내 낸다.
- `sync.py`는 `client` 결과를 `PostIn`으로 바꿔 `ingest`에 넘긴다. 저장 규칙(학년도·임기·중복)은 `ingest`/`terms`만 안다.
- A(내보내기 가져오기)는 나중에 `collectors/instagram_export/`를 만들어 `PostIn`만 넘기면 된다.

## 6. 흐름

### 6.1 계정 연결 (최초 1회, 운영자)
1. 관리자가 `GET /admin/organizations/{slug}/instagram/connect-url` → 연결 링크를 운영자에게 전달.
   - 링크: `https://www.instagram.com/oauth/authorize?client_id=…&redirect_uri=…&response_type=code&scope=instagram_business_basic&state=<서명된 org slug>`
2. 운영자가 로그인·동의 → `GET /integrations/instagram/callback?code=…&state=…`
3. 서버: state 서명 검증(위조·만료 시 거부) → `POST https://api.instagram.com/oauth/access_token`로 단기 토큰(1시간) → `GET graph.instagram.com/access_token?grant_type=ig_exchange_token`로 장기 토큰(60일) → `/me?fields=user_id,username`로 계정 확인 → channel 생성/토큰 교체 → 바로 전체 수집(6.2) 실행.

### 6.2 동기화 (`python -m app.cli sync-instagram [--org slug] [--full]`)
1. `GET /me/media?fields=id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,username,children{id,media_type,media_url,thumbnail_url}&limit=50`, `paging.next`를 따라간다 (최신순).
2. 기본(증분): 이미 저장된 `media_id`를 만나면 멈춘다. `--full`: 끝까지 돌며 캡션 수정 등을 반영.
3. 새 게시물마다 미디어 파일을 내려받아 저장소에 올린다. API의 `media_url`은 **만료되는 CDN 링크**라 반드시 복사해 둔다.
   - `media_url`이 없으면(저작권 음원 릴스 등) `thumbnail_url` → 그것도 없으면 `permalink`만 저장.
4. `PostIn` → `ingest.upsert` (학년도 계산, 임기 배정, `dedupe_key`로 중복 방지).
5. 끝나면 `channels.last_synced_at` 갱신.

### 6.3 토큰 갱신 (`python -m app.cli refresh-tokens`, 하루 1회 cron)
- 만료 10일 이내 토큰을 `GET graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token`로 갱신.

### 6.4 오류 처리
| 상황 | 처리 |
|---|---|
| 토큰 만료·취소 (OAuthException, code 190) | channel `needs_reauth`, 그 채널만 건너뜀. 관리자에게 재연결 링크 필요 |
| 호출 한도 (HTTP 429, code 4/17/32) | 지수 백오프 후 재시도, 3회 실패 시 이번 실행 중단 (다음 실행에 이어서) |
| 미디어 다운로드 실패 | 게시물은 저장, 해당 미디어는 `storage_key = NULL`로 남기고 `--full` 때 재시도 |
| 한 채널 실패 | 다른 채널 동기화는 계속 진행 |

## 7. 구성원·권한 (후속 범위, 방향만)

- `memberships(organization_id, term_id, person, role, title, status, approved_by)`
- `role = lead` (학생회장·부회장·동아리장·조교): 관리자가 임기마다 지정.
- `role = member`: 본인이 신청 → 같은 임기의 lead가 승인(`pending → approved/rejected`).
- 임기 단위로 묶어 기수가 바뀌면 권한이 자연스럽게 넘어가고, 지난 기수 명단은 기록으로 남는다.
- 그때까지 관리 API는 `ADMIN_TOKEN` 헤더로만 보호한다.

## 8. API (이번 범위)

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/organizations` | 조직 목록 |
| GET | `/organizations/{slug}/years` | 학년도별 게시물 수 |
| GET | `/organizations/{slug}/archive?academic_year=2026` | 임기별로 묶은 게시물 + 임기 미지정 |
| GET | `/media/{key}` | 저장소에서 읽어 전달하는 미디어 파일 |
| POST | `/admin/organizations` | 조직 생성 |
| POST/PATCH/DELETE | `/admin/organizations/{slug}/terms[/{id}]` | 임기 관리 (재배정 실행) |
| PATCH | `/admin/posts/{id}` | 게시물 임기 수동 지정·고정 |
| GET | `/admin/organizations/{slug}/instagram/connect-url` | 연결 링크 발급 |
| DELETE | `/admin/channels/{id}[?purge=true]` | 기본: 채널 행은 남기고 `disconnected`로 바꾸며 토큰을 지운다(게시물은 그대로 채널에 연결, 이후 purge 가능). `purge=true`: 그 채널 게시물·미디어 파일·채널 행을 모두 삭제 (운영자 요청 시 기록 삭제). 같은 조직이 같은 계정을 다시 연결하면 `active`로 복구된다 |
| GET | `/integrations/instagram/callback` | OAuth 콜백 |

## 9. 환경변수 (`.env.example`에 이름만 추가)

`INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`, `INSTAGRAM_REDIRECT_URI`, `INSTAGRAM_API_VERSION`, `TOKEN_ENCRYPTION_KEY`, `STATE_SECRET`, `OAUTH_STATE_MAX_AGE`(초, 기본 259200=72시간), `ADMIN_TOKEN`, `MEDIA_STORAGE`(`local`|`ncp`), `MEDIA_LOCAL_DIR`(기본 `data/raw/media`, gitignore), `NCP_OBJECT_STORAGE_ENDPOINT`

## 10. 테스트

실제 인스타그램은 호출하지 않는다. `pytest` + `respx`(HTTP 모킹) + SQLite 메모리 DB.

- 학년도: 2/28·2/29(윤년)·3/1 경계, UTC→KST 날짜 넘어가는 경우
- 임기: 배정, 겹침 거부, 임기 수정 시 재배정, `term_locked` 유지, 임기 없는 게시물
- 동기화: 페이지 넘김, 캐러셀 children, `media_url` 없는 게시물, 증분 중단, 재실행 시 중복 없음
- 토큰: 장기 토큰 교환, 갱신 대상 선별, code 190 → `needs_reauth`, 429 백오프
- OAuth: state 위조·만료 거부
- 조회 API: 학년도·임기별 묶음 응답 형태

테스트용 응답은 `data/samples/instagram/`에 **더미 데이터**로 둔다 (실제 게시물 복사 금지).

수동 확인 (토큰 발급 후): 3개 계정 연결 → 전체 수집 → 게시물 수가 프로필 표시 수와 맞는지, 캡션 존재 여부, 학년도·임기 배정 확인.

## 11. 작업 단위 (PR 분할)

1. 백엔드 뼈대 + 모델 + 학년도·임기 규칙 + `ingest` + seed
2. 인스타 client + sync + 저장소 + CLI
3. OAuth 연결 + 토큰 갱신 + 조회·관리 API

## 12. 확인 필요

- [ ] 제38대 '은하' 임기 시작·종료일, 이전 기수(제37대 등) 이름과 기간 → seed 데이터
- [ ] Meta 개발자 앱을 누구 계정으로 만들지 (BE 담당 권장)
- [ ] 세 계정 운영자 연락·프로페셔널 전환·테스터 수락 일정 (PM)
