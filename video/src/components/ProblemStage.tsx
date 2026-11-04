import React from "react";
import { AbsoluteFill } from "remotion";
import { C, fontFamily } from "../theme";

// 문제 장면 공통 배경 + 우측 상단 에피소드 표시
export const ProblemStage: React.FC<{ ep: string; children: React.ReactNode }> = ({
  ep,
  children,
}) => (
  <AbsoluteFill
    style={{
      background: `radial-gradient(circle at 30% 50%, ${C.nightField}, ${C.night} 75%)`,
      fontFamily,
    }}
  >
    <div
      style={{
        position: "absolute",
        right: 100,
        top: 80,
        fontSize: 30,
        fontWeight: 700,
        letterSpacing: "0.08em",
        color: C.nightMuted,
        opacity: 0.8,
      }}
    >
      {ep}
    </div>
    {children}
  </AbsoluteFill>
);
