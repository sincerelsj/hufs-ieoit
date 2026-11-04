import React from "react";
import { AbsoluteFill, interpolate, random, useCurrentFrame } from "remotion";
import { Caption } from "../components/Caption";
import { Logo } from "../components/Logo";
import accounts from "../data/accounts.json";
import { C, clamp, fontFamily, inOut, out } from "../theme";

// 해결 ② 161개 계정의 게시물을 이어:잇이 한 곳으로 모은다.
const KIND_COLOR: Record<string, string> = {
  학생회: "#1f5f8b",
  학과사무실: "#2f7d5b",
  "동아리/학회": "#8a4fb0",
  기타: "#7a6a55",
};

const CX = 960;
const CY = 690;

export const Gather: React.FC = () => {
  const frame = useCurrentFrame();
  const arrived = accounts.filter((_, i) => frame >= 52 + (i % 40) * 1.4 + 24).length;

  return (
    <AbsoluteFill name="Gather" style={{ background: C.page, fontFamily, overflow: "hidden" }}>
      {accounts.map((a, i) => {
        // 가운데 카드를 비켜 가도록 바깥쪽에 흩뿌린다
        const angle = random(`a${i}`) * Math.PI * 2;
        const r = 0.45 + random(`r${i}`) * 0.55;
        const x = CX + Math.cos(angle) * 900 * r;
        const y = CY + Math.sin(angle) * 330 * r;
        const pop = (i % 40) * 0.6;
        const leave = 52 + (i % 40) * 1.4;
        const t = interpolate(frame, [leave, leave + 24], [0, 1], { ...clamp, easing: inOut });

        return (
          <div
            key={a.u}
            style={{
              position: "absolute",
              left: x + (CX - x) * t,
              top: y + (CY - y) * t,
              translate: "-50% -50%",
              padding: "6px 14px",
              borderRadius: 999,
              background: "#fff",
              border: `2px solid ${KIND_COLOR[a.k] ?? C.muted}`,
              color: KIND_COLOR[a.k] ?? C.muted,
              fontSize: 20,
              fontWeight: 700,
              whiteSpace: "nowrap",
              opacity: interpolate(frame, [pop, pop + 8], [0, 1], clamp) * (1 - t * t),
              scale: interpolate(frame, [pop, pop + 12], [0.4, 1], { ...clamp, easing: out }) * (1 - 0.7 * t),
            }}
          >
            @{a.u}
          </div>
        );
      })}

      <div
        style={{
          position: "absolute",
          left: CX,
          top: CY,
          translate: "-50% -50%",
          width: 600,
          padding: "44px 40px",
          borderRadius: 36,
          background: C.night,
          color: C.nightInk,
          textAlign: "center",
          boxShadow: `0 0 0 ${interpolate(frame, [70, 110], [0, 14], clamp)}px ${C.thread}55, 0 40px 90px rgba(18,35,58,0.35)`,
          opacity: interpolate(frame, [30, 44], [0, 1], clamp),
          scale: interpolate(frame, [30, 50], [0.85, 1], { ...clamp, easing: out }),
        }}
      >
        <Logo size={96} color={C.nightInk} />
        <div style={{ marginTop: 26, fontSize: 92, fontWeight: 900, color: C.thread, lineHeight: 1 }}>
          {arrived}
          <span style={{ fontSize: 40, fontWeight: 700, color: C.nightMuted }}> / 161 계정</span>
        </div>
        <div style={{ marginTop: 18, fontSize: 30, color: C.nightMuted }}>
          학년도·행사별로 자동 정리
        </div>
      </div>

      <Caption
        kicker="해결 ② 우리가 한데 모음"
        lines={["기록은 이어:잇이 모아 아카이빙"]}
        from={4}
        dark={false}
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 70,
          textAlign: "center",
          background: `linear-gradient(${C.page} 75%, ${C.page}00)`,
          paddingBottom: 30,
        }}
      />
    </AbsoluteFill>
  );
};
