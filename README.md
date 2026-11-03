# HUFS 이어:잇

> **AI 기반 학내 활동 기록 및 인수인계 아카이빙 플랫폼**
> "사람은 매년 바뀌지만, 대학의 경험까지 매년 초기화될 필요는 없다."

학생회·학과 사무실의 활동 기록(SNS 게시물, 학과 공지 등)을 자동으로 모아 연도·조직별로 정리하고, HyperCLOVA X로 요약·분류·검색·인수인계 문서 생성을 지원하는 서비스입니다.

**2026 AI 캠퍼스: 바이브코딩 경진대회** (한국외국어대학교 × 네이버클라우드) 출품작입니다. → [대회 안내](https://contest.hufs.ac.kr/) · [대회 요약](docs/contest.md) · [제안서](docs/proposal.md)

---

## 📌 이 레포가 프로젝트의 기준입니다 (Single Source of Truth)

이 프로젝트는 **GitHub 레포를 중심으로 운영**합니다. 카톡·노션·개인 PC에 흩어진 내용은 "결정된 것"으로 보지 않습니다.

| 무엇을 | 어디에 |
|---|---|
| 코드, 문서, 기획·결정 사항 | 이 레포 (`main` 브랜치 기준) |
| 할 일, 버그, 아이디어 | [Issues](../../issues) — 담당자·라벨·마일스톤 지정 |
| 진행 현황 | [Projects 보드](../../projects) / 마일스톤 |
| 변경 리뷰·합의 | Pull Request (main 직접 push 금지) |
| 회의록·주요 결정 | `docs/meetings/`, `docs/decisions/` |
| 비밀값(API 키 등) | **레포에 절대 X** → 팀 내부 채널로만 공유, 로컬 `.env` 사용 |

> 카톡에서 정한 게 있으면 → 이슈나 회의록으로 옮겨야 "확정"입니다.
> 바이브코딩으로 만든 코드도 반드시 PR로 올리고 리뷰를 받습니다.

---

## 👥 팀 & 역할

| 역할 | 담당 | 소속 | 주요 업무 | 주 작업 폴더 |
|---|---|---|---|---|
| PM / 기획 · AI Agent | 이승주 | AI융합학과 석사과정 | 일정·이슈 관리, 기획서·결과보고서, 학생회/학과 데이터 확보, CLOVA Studio 연동(분류·요약·검색·인수인계 생성) | `docs/`, `backend/app/ai/` |
| Backend | 박성재 | 컴퓨터공학 학부 | API, DB, 수집기(크롤러), NCP 배포 | `backend/` |
| Frontend | 음유현 | AI융합학과 석사과정 | 아카이브 페이지, 검색 UI, 인수인계 문서 화면 | `frontend/` |
| QA, 외국인 유학생 시점 | 궈이판 | 미디어커뮤니케이션학과 박사과정 | 테스트 시나리오, 버그 리포트, 사용성 검증(외국인 유학생 시점 포함), 발표 데모 리허설 | `qa/` |

- 4인 팀 (대회 규정 최대 5인). 한 사람이 역할을 겸할 수 있습니다.
- 역할별 코드 소유자는 [`.github/CODEOWNERS`](.github/CODEOWNERS)에 GitHub ID를 채워 주세요.

---

## 🧩 주요 기능 (MVP 범위)

1. **자동 아카이빙** — 학과 홈페이지 공지·학생회 SNS 게시물 수집 → 조직·연도별 정리
2. **AI 기록 정리** — 행사/업무/공지 자동 분류 및 요약 (HyperCLOVA X)
3. **통합 검색** — 자연어로 과거 활동·졸업요건·학사 공지 검색
4. **인수인계 지원** — 과거 기록 + 담당자 노하우 → 인수인계 문서 자동 생성 (권한 있는 사용자만)

> 인스타그램은 공식 API 권한·정책에 따라 제한될 수 있으므로 **허용된 계정 연동 + 직접 등록**을 병행합니다.

---

## 🛠 기술 스택

| 영역 | 스택 |
|---|---|
| Frontend | Next.js (TypeScript), Tailwind CSS |
| Backend | FastAPI (Python 3.11+), SQLAlchemy |
| DB | PostgreSQL (NCP Cloud DB) · 로컬은 SQLite/Docker |
| AI | NAVER CLOVA Studio — HyperCLOVA X (요약·분류·생성), 임베딩(검색) |
| Infra | NAVER Cloud Platform (Server, Object Storage) |
| 개발 도구 | Claude, ChatGPT (바이브코딩) |

> 네이버클라우드 활용 시 심사 가점(최대 5점) 대상이므로 AI·인프라는 NCP를 우선 사용합니다.

---

## 📁 폴더 구조

```
hufs-ieoit/
├── frontend/          # Next.js 웹 (FE)
├── backend/           # FastAPI 서버 (BE)
│   └── app/ai/        # CLOVA Studio 연동 (AI)
├── qa/                # 테스트 시나리오, 체크리스트 (QA)
├── data/              # 샘플/더미 데이터만 (실데이터 커밋 금지)
├── docs/              # 기획서, 대회 정보, 회의록, 결정 기록
│   ├── meetings/
│   └── decisions/
├── .github/           # 이슈·PR 템플릿, CODEOWNERS
├── AGENTS.md          # AI 코딩 도구(Claude/ChatGPT/Cursor)용 프로젝트 규칙
└── CONTRIBUTING.md    # 협업 규칙 (브랜치·커밋·PR)
```

---

## 🗓 일정 (대회 기준)

| 날짜 | 내용 | 마일스톤 |
|---|---|---|
| ~ 11/10 (화) | 참가신청서·기획서 온라인 접수 | `M0 예선 접수` |
| 11/11 ~ 11/13 | 예선 서류 평가 | |
| 11/16 (월) | 본선 진출팀 발표 (10팀) | |
| 11/18 (수) | 네이버클라우드 사전교육 | |
| 11/16 ~ 11/27 | MVP 개발 (수집·아카이브·검색) | `M1 MVP` |
| 11/28 ~ 12/6 | AI 기능 고도화·QA·결과보고서 | `M2 본선 제출` |
| 12/9 (수) | 발표 평가 (발표 10분 + Q&A 5분), 시상식 | `M3 발표` |

※ 대회 일정은 운영 상황에 따라 바뀔 수 있습니다. 최신 일정은 [대회 사이트](https://contest.hufs.ac.kr/) 확인.

---

## 🚀 시작하기

```bash
git clone https://github.com/<OWNER>/hufs-ieoit.git
cd hufs-ieoit
cp .env.example .env   # 키는 팀 채널에서 받아 채우기
```

- 프론트엔드: [`frontend/README.md`](frontend/README.md)
- 백엔드: [`backend/README.md`](backend/README.md)
- QA: [`qa/README.md`](qa/README.md)

처음이라면 **[CONTRIBUTING.md](CONTRIBUTING.md)** 를 먼저 읽어 주세요. 전체 계획과 도식은 **[프로젝트 계획서](docs/project-plan.md)** 에 있습니다.

---

## 🔒 데이터·보안 원칙

- 실제 학생 개인정보, 내부 인수인계 원문, API 키는 **커밋 금지** (공개 레포입니다).
- `data/`에는 익명화된 샘플·더미 데이터만 둡니다.
- AI 도구에 개인정보나 키를 붙여넣지 않습니다.
- 내부 인수인계 자료는 서비스에서 별도 접근 권한을 적용합니다.
- 생성형 AI 도구·모델의 라이선스와 이용약관을 지킵니다 (위반 시 수상 제외 규정).
