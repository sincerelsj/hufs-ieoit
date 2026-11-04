import React from "react";
import { AbsoluteFill, Interactive, interpolate, useCurrentFrame } from "remotion";
import { Logo } from "../components/Logo";
import { C, clamp, fontFamily, inOut, out } from "../theme";

// 문제 → 해결 전환. 금색 실 한 줄이 화면을 가르고, 밝은 종이 위로 이어:잇이 나타난다.
export const Turn: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill name="Turn" style={{ background: C.night, fontFamily }}>
      <AbsoluteFill
        name="Thread"
        style={{ justifyContent: "center", alignItems: "flex-start" }}
      >
        <div
          style={{
            height: 8,
            borderRadius: 8,
            background: C.thread,
            boxShadow: `0 0 30px ${C.thread}`,
            width: `${interpolate(frame, [0, 28], [0, 100], { ...clamp, easing: inOut })}%`,
          }}
        />
      </AbsoluteFill>
      <AbsoluteFill
        name="Paper"
        style={{
          background: C.page,
          clipPath: `inset(${interpolate(frame, [26, 50], [50, 0], { ...clamp, easing: inOut })}% 0)`,
        }}
      />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
        <Interactive.Div
          name="Logo"
          style={{
            opacity: interpolate(frame, [42, 56], [0, 1], clamp),
            scale: interpolate(frame, [42, 70], [0.8, 1], {
              ...clamp,
              easing: out,
              output: "perceptual-scale",
            }),
          }}
        >
          <Logo size={220} />
        </Interactive.Div>
        <Interactive.Div
          name="Tagline"
          style={{
            marginTop: 40,
            fontSize: 56,
            fontWeight: 700,
            color: C.muted,
            opacity: interpolate(frame, [60, 76], [0, 1], clamp),
            translate: interpolate(frame, [60, 84], ["0px 20px", "0px 0px"], { ...clamp, easing: out }),
          }}
        >
          흩어진 학교의 기록을, 한 곳에
        </Interactive.Div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
