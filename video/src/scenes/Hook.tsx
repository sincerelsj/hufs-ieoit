import React from "react";
import { AbsoluteFill, Interactive, interpolate, useCurrentFrame } from "remotion";
import { C, clamp, fontFamily, out } from "../theme";

export const Hook: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill
      name="Hook"
      style={{
        background: `radial-gradient(circle at 50% 45%, ${C.nightField}, ${C.night} 70%)`,
        justifyContent: "center",
        alignItems: "center",
        fontFamily,
        color: C.nightInk,
      }}
    >
      <Interactive.Div
        name="Line1"
        style={{
          fontSize: 64,
          fontWeight: 500,
          color: C.nightMuted,
          opacity: interpolate(frame, [6, 26], [0, 1], clamp),
          translate: interpolate(frame, [6, 36], ["0px 24px", "0px 0px"], { ...clamp, easing: out }),
        }}
      >
        그때의 우리는
      </Interactive.Div>
      <Interactive.Div
        name="Line2"
        style={{
          marginTop: 12,
          fontSize: 120,
          fontWeight: 900,
          letterSpacing: "-0.03em",
          opacity: interpolate(frame, [22, 44], [0, 1], clamp),
          translate: interpolate(frame, [22, 54], ["0px 30px", "0px 0px"], { ...clamp, easing: out }),
        }}
      >
        어디로 갔을까
      </Interactive.Div>
    </AbsoluteFill>
  );
};
