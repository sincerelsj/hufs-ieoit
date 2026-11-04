import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import years from "../data/years.json";
import { C, clamp, fontFamily, out } from "../theme";

// 해결 ③ 연감 서가(A안) — 학년도별 책 9권 중 한 권을 꺼내 펼친다.
const PICK = 2023;
const SPINE_COLORS = ["#1f5f8b", "#2b4a6f", "#3d6d8f", "#25405f", "#4a7fa3", "#1f5f8b", "#2b4a6f", "#3d6d8f", "#25405f"];

export const Yearbook: React.FC = () => {
  const frame = useCurrentFrame();
  const book = years.find((y) => y.y === PICK)!;
  const lift = interpolate(frame, [48, 70], [0, 1], { ...clamp, easing: out });
  const open = interpolate(frame, [70, 100], [0, 1], { ...clamp, easing: out });
  const maxCat = book.cats[0][1] as number;

  return (
    <AbsoluteFill
      name="Yearbook"
      style={{
        background: `radial-gradient(circle at 30% 40%, ${C.nightField}, ${C.night} 75%)`,
        fontFamily,
      }}
    >
      <div style={{ position: "absolute", left: 110, top: 80 }}>
        <div
          style={{
            display: "inline-block",
            padding: "10px 22px",
            borderRadius: 999,
            background: C.thread,
            color: C.ink,
            fontSize: 34,
            fontWeight: 700,
            opacity: interpolate(frame, [0, 12], [0, 1], clamp),
          }}
        >
          해결 ③ 학년도별 연감
        </div>
        <div
          style={{
            marginTop: 24,
            fontSize: 76,
            fontWeight: 900,
            lineHeight: 1.2,
            color: C.nightInk,
            opacity: interpolate(frame, [8, 22], [0, 1], clamp),
            translate: interpolate(frame, [8, 30], ["0px 30px", "0px 0px"], { ...clamp, easing: out }),
          }}
        >
          그때의 우리를,
          <br />
          언제든 다시
        </div>
      </div>

      {/* 서가 */}
      <div style={{ position: "absolute", left: 110, bottom: 110, display: "flex", alignItems: "flex-end", gap: 12 }}>
        {years.map((y, i) => {
          const picked = y.y === PICK;
          return (
            <div
              key={y.y}
              style={{
                width: 80,
                height: 230 + y.count * 1.2,
                borderRadius: "8px 8px 4px 4px",
                background: SPINE_COLORS[i],
                border: `4px solid ${picked && lift > 0.1 ? C.thread : "transparent"}`,
                boxShadow: picked ? `0 0 ${lift * 40}px ${C.thread}` : "inset -10px 0 0 rgba(0,0,0,0.12)",
                color: C.nightInk,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                paddingTop: 18,
                gap: 12,
                opacity: interpolate(frame, [4 + i * 3, 14 + i * 3], [0, 1], clamp),
                translate: `0px ${interpolate(frame, [4 + i * 3, 22 + i * 3], [40, 0], { ...clamp, easing: out }) - (picked ? lift * 46 : 0)}px`,
              }}
            >
              <div style={{ fontSize: 22, fontWeight: 900 }}>{y.y}</div>
              <div style={{ writingMode: "vertical-rl", fontSize: 26, fontWeight: 700, color: picked ? C.thread : C.nightMuted }}>
                제{y.gen}대 {y.name}
              </div>
            </div>
          );
        })}
      </div>
      <div
        style={{
          position: "absolute",
          left: 90,
          width: 900,
          bottom: 84,
          height: 26,
          borderRadius: 6,
          background: C.wood,
          borderBottom: `8px solid ${C.woodDark}`,
          opacity: interpolate(frame, [0, 10], [0, 1], clamp),
        }}
      />

      {/* 펼친 연감 */}
      <div
        style={{
          position: "absolute",
          right: 100,
          top: 90,
          width: 780,
          height: 900,
          borderRadius: 18,
          background: C.page,
          color: C.ink,
          padding: "44px 48px",
          boxShadow: "0 40px 100px rgba(0,0,0,0.45)",
          opacity: open,
          translate: `${(1 - open) * 120}px 0px`,
          rotate: `${(1 - open) * 4}deg`,
        }}
      >
        <div style={{ fontSize: 28, fontWeight: 700, color: C.accent }}>미디어커뮤니케이션학부 학생회</div>
        <div style={{ marginTop: 6, fontSize: 54, fontWeight: 900, letterSpacing: "-0.02em", whiteSpace: "nowrap" }}>
          {book.y}학년도 · 제{book.gen}대 ‘{book.name}’
        </div>
        <div style={{ marginTop: 8, fontSize: 28, color: C.muted }}>
          게시물 {book.count}건 · 2023.03 – 2024.02
        </div>

        <div style={{ marginTop: 34, display: "flex", flexDirection: "column", gap: 12 }}>
          {book.cats.slice(0, 5).map(([name, n], j) => (
            <div key={name as string} style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 26 }}>
              <div style={{ width: 120, fontWeight: 700 }}>{name}</div>
              <div
                style={{
                  height: 22,
                  borderRadius: 11,
                  background: j === 0 ? C.thread : C.accent,
                  width: interpolate(frame, [90 + j * 4, 120 + j * 4], [0, ((n as number) / maxCat) * 460], {
                    ...clamp,
                    easing: out,
                  }),
                }}
              />
              <div style={{ color: C.muted }}>{n}</div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 36, display: "flex", gap: 18 }}>
          {book.picks.slice(0, 3).map((p, j) => (
            <div
              key={p.d}
              style={{
                flex: 1,
                opacity: interpolate(frame, [110 + j * 8, 124 + j * 8], [0, 1], clamp),
                translate: interpolate(frame, [110 + j * 8, 134 + j * 8], ["0px 30px", "0px 0px"], {
                  ...clamp,
                  easing: out,
                }),
              }}
            >
              <div style={{ aspectRatio: "1", borderRadius: 12, overflow: "hidden", background: C.pageLine }}>
                {p.img ? (
                  <Img src={staticFile(p.img)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                ) : null}
              </div>
              <div style={{ marginTop: 10, fontSize: 20, fontWeight: 700, color: C.threadInk }}>
                {p.c} · {p.d.slice(5).replace("-", ".")}
              </div>
            </div>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};
