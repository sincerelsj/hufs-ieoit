import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { Caption } from "../components/Caption";
import { C, clamp, fontFamily, out } from "../theme";

// 해결 ① 각 단체는 하던 대로 인스타에 올리기만 하면 된다.
const PHONES = [
  {
    u: "hufs_mecomm",
    k: "학생회",
    tint: "#dfe8f3",
    photos: ["archive/y2025-1.jpg", "archive/y2024-1.jpg", "archive/y2023-1.jpg", "archive/y2025-0.jpg", "archive/y2024-0.jpg", "archive/y2023-0.jpg"],
    fresh: "archive/y2026-1.jpg",
    at: 40,
  },
  { u: "hufs_aidata", k: "학과 사무실", tint: "#efe6d6", photos: [], fresh: "", at: 62 },
  { u: "beatholic_official", k: "동아리", tint: "#e8e1f2", photos: [], fresh: "", at: 84 },
];

const Phone: React.FC<{ p: (typeof PHONES)[number]; i: number }> = ({ p, i }) => {
  const frame = useCurrentFrame();
  const tiles = Array.from({ length: 9 }, (_, j) => p.photos[j] ?? "");

  return (
    <div
      style={{
        width: 300,
        height: 610,
        borderRadius: 44,
        background: "#1d2433",
        padding: 12,
        boxShadow: "0 30px 70px rgba(20,32,51,0.25)",
        opacity: interpolate(frame, [i * 8, i * 8 + 14], [0, 1], clamp),
        translate: interpolate(frame, [i * 8, i * 8 + 26], ["0px 60px", "0px 0px"], {
          ...clamp,
          easing: out,
        }),
      }}
    >
      <div
        style={{
          width: "100%",
          height: "100%",
          borderRadius: 34,
          background: "#fff",
          overflow: "hidden",
          fontFamily,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "34px 18px 14px" }}>
          <div
            style={{
              width: 50,
              height: 50,
              borderRadius: 25,
              background: "linear-gradient(45deg,#f9b234,#e1306c,#833ab4)",
              padding: 3,
            }}
          >
            <div style={{ width: "100%", height: "100%", borderRadius: 22, background: p.tint }} />
          </div>
          <div>
            <div style={{ fontSize: 19, fontWeight: 700, color: C.ink }}>@{p.u}</div>
            <div style={{ fontSize: 16, color: C.muted }}>{p.k}</div>
          </div>
        </div>
        <div style={{ position: "relative", display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 3 }}>
          {tiles.map((src, j) => (
            <div key={j} style={{ aspectRatio: "1", background: p.tint, overflow: "hidden" }}>
              {src ? (
                <Img src={staticFile(src)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              ) : null}
            </div>
          ))}
          {/* 새 게시물이 맨 앞에 올라온다 */}
          <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            width: "calc(33.3% - 2px)",
            aspectRatio: "1",
            background: p.fresh ? "#000" : C.thread,
            overflow: "hidden",
            outline: `4px solid ${C.thread}`,
            outlineOffset: -4,
            opacity: interpolate(frame, [p.at, p.at + 6], [0, 1], clamp),
            scale: interpolate(frame, [p.at, p.at + 16], [1.6, 1], { ...clamp, easing: out }),
          }}
        >
          {p.fresh ? (
            <Img src={staticFile(p.fresh)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          ) : null}
          </div>
        </div>
      </div>
      <div
        style={{
          marginTop: 26,
          textAlign: "center",
          fontFamily,
          fontSize: 30,
          fontWeight: 700,
          color: C.threadInk,
          opacity: interpolate(frame, [p.at + 6, p.at + 16], [0, 1], clamp),
        }}
      >
        새 게시물 업로드 ✓
      </div>
    </div>
  );
};

export const KeepPosting: React.FC = () => (
  <AbsoluteFill name="KeepPosting" style={{ background: C.page }}>
    <Caption
      kicker="해결 ① 지금처럼 그대로"
      lines={["각 단체는", "하던 대로", "인스타에 올리면 끝"]}
      from={6}
      dark={false}
      style={{ position: "absolute", left: 110, top: 270 }}
    />
    <div
      style={{
        position: "absolute",
        right: 110,
        top: 180,
        display: "flex",
        gap: 34,
      }}
    >
      {PHONES.map((p, i) => (
        <Phone key={p.u} p={p} i={i} />
      ))}
    </div>
  </AbsoluteFill>
);
