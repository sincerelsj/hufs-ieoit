# 이어:잇 프로토타입 영상

[Remotion](https://www.remotion.dev/)으로 만든 56초짜리 소개 영상입니다 (1920×1080, 30fps).
완성본: [`docs/media/ieoit-prototype.mp4`](../docs/media/ieoit-prototype.mp4)

## 장면 구성

| 장면 | 파일 | 길이 | 내용 |
|---|---|---|---|
| Hook | `src/scenes/Hook.tsx` | 3초 | 그때의 우리는 어디로 갔을까 |
| EP.1 | `src/scenes/Ep1.tsx` | 9초 | 사라진 추억 — 1·2컷 빠르게, 3컷에 머묾 |
| EP.2 | `src/scenes/Ep2.tsx` | 8초 | 전설의 조교 — 빈 인수인계 서랍, 학교가 펑 |
| EP.3 | `src/scenes/Ep3.tsx` | 12초 | 놓쳐버린 공지 — 네 컷 차례로 |
| Turn | `src/scenes/Turn.tsx` | 4초 | 이어:잇 로고 등장 |
| 해결 ① | `src/scenes/KeepPosting.tsx` | 6초 | 각 단체는 지금처럼 인스타에 올리면 끝 |
| 해결 ② | `src/scenes/Gather.tsx` | 6초 | 161개 계정을 한 곳으로 |
| 해결 ③ | `src/scenes/Yearbook.tsx` | 7초 | 학년도별 연감(A안) |
| Outro | `src/scenes/Outro.tsx` | 5초 | 로고·한국외대·네이버클라우드 |

장면 길이는 `src/IeoitVideo.tsx`의 `SCENES`에서, 색과 글꼴은 `src/theme.ts`에서 바꿉니다. 장면 사이는 0.5초 페이드로 겹칩니다.

## 실행

```bash
cd video
npm i
npm run dev                                              # Remotion Studio 미리보기
npx remotion render IeoitPrototype out/ieoit-prototype.mp4  # mp4 만들기
```

## BGM

`public/bgm.mp3`(또는 `.wav`, `.m4a`)를 넣고 다시 렌더하면 음악이 깔립니다. 파일이 없으면 무음으로 렌더됩니다.
문제 장면에서는 작게, 이어:잇 로고부터 크게, 마지막 2초에 줄어듭니다 (`src/components/Bgm.tsx`).
저작권이 해결된 음원만 쓰세요.

## 사용한 자료

- `public/webtoon/`: 네컷 웹툰 EP.1~3을 컷별로 자른 이미지 (생성형 AI로 제작)
- `public/archive/`: 미디어커뮤니케이션학부 학생회 공개 인스타그램 게시물 썸네일 (학년도 아카이브 시안과 같은 이미지)
- `public/logo/`: 한국외대·네이버클라우드 공식 로고 파일
- `src/data/accounts.json`: 한국외대 공개 인스타그램 계정 161개 목록 (기관·단체 계정만)
- `src/data/years.json`: 미컴 학생회 게시물 1,261건의 학년도별 집계
