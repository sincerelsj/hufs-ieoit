import React from "react";
import { C, fontFamily } from "../theme";

// 이어:잇 글자 로고. 쌍점(:)은 '잇는 실' 색으로 둔다.
export const Logo: React.FC<{ size: number; color?: string }> = ({
  size,
  color = C.ink,
}) => (
  <div
    style={{
      fontFamily,
      fontSize: size,
      fontWeight: 900,
      letterSpacing: "-0.04em",
      color,
      lineHeight: 1,
      whiteSpace: "nowrap",
    }}
  >
    이어<span style={{ color: C.thread, margin: "0 0.04em" }}>:</span>잇
  </div>
);
