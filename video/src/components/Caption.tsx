import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { C, clamp, fontFamily, out } from "../theme";

// 문제 장면 오른쪽에 붙는 자막. kicker(작은 머리말) + 큰 문장.
export const Caption: React.FC<{
  kicker: string;
  lines: string[];
  from?: number;
  to?: number; // 이 프레임부터 사라짐 (없으면 계속 보임)
  dark?: boolean;
  style?: React.CSSProperties;
}> = ({ kicker, lines, from = 0, to, dark = true, style }) => {
  const frame = useCurrentFrame();
  const fadeOut =
    to === undefined ? 1 : interpolate(frame, [to, to + 10], [1, 0], clamp);

  return (
    <div style={{ fontFamily, ...style, opacity: fadeOut }}>
      <div
        style={{
          display: "inline-block",
          padding: "10px 22px",
          borderRadius: 999,
          background: C.thread,
          color: C.ink,
          fontSize: 34,
          fontWeight: 700,
          opacity: interpolate(frame, [from, from + 12], [0, 1], clamp),
          translate: interpolate(frame, [from, from + 18], ["0px 20px", "0px 0px"], {
            ...clamp,
            easing: out,
          }),
        }}
      >
        {kicker}
      </div>
      {lines.map((line, i) => (
        <div
          key={line}
          style={{
            marginTop: i === 0 ? 34 : 6,
            fontSize: 84,
            lineHeight: 1.22,
            fontWeight: 900,
            letterSpacing: "-0.02em",
            color: dark ? C.nightInk : C.ink,
            opacity: interpolate(frame, [from + 8 + i * 6, from + 22 + i * 6], [0, 1], clamp),
            translate: interpolate(
              frame,
              [from + 8 + i * 6, from + 30 + i * 6],
              ["0px 36px", "0px 0px"],
              { ...clamp, easing: out },
            ),
          }}
        >
          {line}
        </div>
      ))}
    </div>
  );
};
