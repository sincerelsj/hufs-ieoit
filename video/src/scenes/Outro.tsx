import React from "react";
import { AbsoluteFill, Img, Interactive, interpolate, staticFile, useCurrentFrame } from "remotion";
import { Logo } from "../components/Logo";
import { C, clamp, fontFamily, out } from "../theme";

export const Outro: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill
      name="Outro"
      style={{ background: C.page, justifyContent: "center", alignItems: "center", fontFamily }}
    >
      <Interactive.Div
        name="Logo"
        style={{
          marginTop: -80,
          opacity: interpolate(frame, [0, 14], [0, 1], clamp),
          scale: interpolate(frame, [0, 30], [0.9, 1], { ...clamp, easing: out, output: "perceptual-scale" }),
        }}
      >
        <Logo size={200} />
      </Interactive.Div>
      <Interactive.Div
        name="Tagline"
        style={{
          marginTop: 44,
          fontSize: 60,
          fontWeight: 700,
          color: C.ink,
          opacity: interpolate(frame, [16, 32], [0, 1], clamp),
          translate: interpolate(frame, [16, 40], ["0px 20px", "0px 0px"], { ...clamp, easing: out }),
        }}
      >
        기록은 이어지고, 추억은 잇는다
      </Interactive.Div>
      <Interactive.Div
        name="Logos"
        style={{
          position: "absolute",
          bottom: 100,
          display: "flex",
          alignItems: "center",
          gap: 56,
          opacity: interpolate(frame, [34, 50], [0, 1], clamp),
        }}
      >
        <Img src={staticFile("logo/hufs.png")} style={{ height: 84 }} />
        <div style={{ width: 2, height: 56, background: C.pageLine }} />
        <Img src={staticFile("logo/naver-cloud.png")} style={{ height: 46 }} />
      </Interactive.Div>
    </AbsoluteFill>
  );
};
