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
pip install -r requirements.txt
uvicorn app.main:app --reload   # http://localhost:8000/docs
```
