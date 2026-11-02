# AGENTS.md — AI 코딩 도구용 프로젝트 규칙

Claude, ChatGPT, Cursor 등 AI 도구로 코드를 작성할 때 이 파일을 함께 제공하세요.

## 프로젝트
- 이름: HUFS 이어:잇 — 학생회·학과 활동 기록 아카이빙 및 인수인계 지원 플랫폼
- 사용자: 한국외대 학생회 임원, 학과 사무실 조교/직원, 재학생
- 언어: UI와 문서는 한국어, 코드 식별자는 영어

## 구조와 스택
- `frontend/`: Next.js (App Router, TypeScript), Tailwind CSS
- `backend/`: FastAPI (Python 3.11+), SQLAlchemy, Pydantic
- `backend/app/ai/`: NAVER CLOVA Studio(HyperCLOVA X) 호출은 이 모듈에서만 한다
- 인프라: NAVER Cloud Platform

## 규칙
- 비밀값은 환경변수로만 읽는다. 키를 코드에 하드코딩하지 않는다. 새 변수는 `.env.example`에 이름만 추가한다.
- 실제 개인정보·학내 원문 데이터를 코드, 테스트, 샘플에 넣지 않는다. 더미 데이터를 쓴다.
- 외부 사이트 수집은 robots.txt와 이용약관을 지키고, 요청 간격을 둔다. 인스타그램은 공식 API만 사용한다.
- 내부 인수인계 자료 API는 인증·권한 확인을 반드시 거친다.
- 새 기능에는 최소한의 테스트를 추가한다 (backend: pytest, frontend: 가능하면 컴포넌트 테스트).
- 기존 폴더 구조와 네이밍을 따른다. 큰 구조 변경은 먼저 이슈로 논의한다.
- 커밋 메시지: `<type>(<scope>): <요약>` — 자세한 규칙은 CONTRIBUTING.md.
