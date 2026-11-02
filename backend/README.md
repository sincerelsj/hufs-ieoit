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
