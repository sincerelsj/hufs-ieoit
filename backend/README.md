# Backend (FastAPI)

담당: BE, AI · 라벨 `BE` `AI`

## 범위 (MVP)
- [ ] 조직·기록(게시물/공지) 데이터 모델
- [ ] 학과 홈페이지 공지 수집기 (robots.txt·이용약관 준수, 요청 간격 유지)
- [ ] 기록 직접 등록 API
- [ ] `app/ai/`: CLOVA Studio — 분류·요약, 임베딩 기반 검색, 인수인계 문서 생성
- [ ] 인수인계 자료 접근 권한
- [ ] NCP 서버 배포

## 세팅 (프로젝트 생성 후 업데이트)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
python -m app.cli seed   # 테이블 생성 + 기본 조직 3개
uvicorn app.main:app --reload   # http://localhost:8000/docs
```

`uvicorn`은 테이블을 만들지 않으므로, API를 처음 실행하기 전에 `seed`를 한 번 실행해야 합니다(여러 번 실행해도 안전합니다).

## Instagram 수집 (Business Discovery, 기본)

수집용 계정 하나의 토큰으로 다른 **공개 비즈니스·크리에이터 계정**의 피드 게시물을 읽습니다. 수집 대상 계정은 로그인·토큰·테스터 초대가 필요 없습니다. 스토리는 가져오지 않습니다.

1. 수집용 인스타 계정(프로페셔널, 공개)을 Facebook 페이지에 연결한다(페이지 설정 → 연결된 계정 → Instagram).
2. Meta 앱 이용 사례 권한: `instagram_basic`, `instagram_manage_insights`, `pages_show_list`, `pages_read_engagement`, `business_management`. 메시지·댓글·게시 권한은 필요 없다.
3. `backend/.env`에 `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`을 넣는다(토큰 변환에 필요).
4. 위 권한으로 사용자 토큰을 받는다(로그인 창에서 페이지와 인스타 계정을 꼭 선택). 그다음 등록한다. 입력은 화면에 보이지 않습니다. 채팅·메신저에 붙여 넣지 마세요.
   ```bash
   python -m app.cli register-collector            # 사용자 토큰 → 60일 토큰 → 만료 없는 페이지 토큰으로 바꿔 암호화 저장
   python -m app.cli add-instagram --org mecomm-council --username hufs_mecomm
   python -m app.cli add-instagram --org mecomm-studio --username hufsmecomm_studio
   python -m app.cli sync-instagram --full
   ```
   Facebook 비밀번호를 바꾸거나 앱 권한을 지우면 페이지 토큰이 무효가 됩니다. 그때는 `register-collector`만 다시 실행하면 됩니다.

## Instagram 계정 연결 (콘솔 토큰, 계정이 직접 토큰을 줄 때)

새 Meta 앱은 Unified login만 쓸 수 있고, 토큰(시스템 사용자 토큰)은 만료되지 않아 계정마다 한 번만 연결합니다. 설계: `docs/specs/2026-11-02-instagram-collector-design.md` §6.1.

1. 인스타 계정을 프로페셔널로 전환하고, 앱 역할에서 **Instagram 테스터**로 초대 → instagram.com 설정 → 앱 및 웹사이트 → 테스터 초대에서 수락.
2. business.facebook.com → 비즈니스 포트폴리오 설정 → 계정 → **Instagram 계정 → 추가**로 계정을 포트폴리오에 넣는다.
3. Meta 콘솔 → Instagram 이용 사례 → API setup with Unified login → **계정 추가 → 토큰 생성**. 광고 계정은 새로 만들지 않는다.
4. 토큰을 복사해 바로 등록한다(입력은 화면에 보이지 않습니다. 채팅·메신저에 붙여 넣지 마세요).
   ```bash
   python -m app.cli register-instagram --org mecomm-studio   # 조직 slug: mecomm-council / mecomm-studio / mecomm-office
   python -m app.cli sync-instagram --org mecomm-studio --full
   ```
