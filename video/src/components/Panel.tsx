import React from "react";
import { Img, staticFile } from "remotion";

// 웹툰 한 컷. 바깥 틀은 고정하고 안쪽 그림만 확대·이동해서 카메라가 움직이는 느낌을 낸다.
export const Panel: React.FC<{
  src: string;
  width: number;
  zoom?: number;
  focus?: string; // transform-origin, 예: "20% 30%"
  style?: React.CSSProperties;
}> = ({ src, width, zoom = 1, focus = "50% 50%", style }) => {
  return (
    <div
      style={{
        width,
        aspectRatio: "600 / 545",
        borderRadius: 28,
        overflow: "hidden",
        border: "5px solid #1d2433",
        boxShadow: "0 30px 80px rgba(0,0,0,0.35)",
        background: "#fff",
        ...style,
      }}
    >
      <Img
        src={staticFile(src)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          scale: String(zoom),
          transformOrigin: focus,
        }}
      />
    </div>
  );
};
