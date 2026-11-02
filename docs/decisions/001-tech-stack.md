# 001. 기술 스택

- 날짜: 2026-11-02
- 상태: 확정

## 배경
FE/BE/AI/QA로 역할을 나눠 협업하고, 대부분 바이브코딩으로 개발한다. 네이버클라우드 활용 시 심사 가점이 있다.

## 결정
- Frontend: Next.js (TypeScript) + Tailwind CSS
- Backend: FastAPI (Python)
- AI: NAVER CLOVA Studio (HyperCLOVA X)
- Infra: NAVER Cloud Platform

## 이유와 대안
- FE/BE를 분리해 역할 경계를 명확히 한다.
- 크롤링, CLOVA Studio 연동, 데이터 처리는 Python 생태계가 편하다.
- 대안: Next.js 풀스택 — 구조는 단순하지만 FE/BE 분담 경계가 흐려져 제외.

## 영향
- 프론트와 백엔드는 REST API로 통신하며, API 명세는 FastAPI 자동 문서(`/docs`)를 기준으로 한다.
