import React from "react";
import { Audio } from "@remotion/media";
import { getStaticFiles, interpolate, staticFile } from "remotion";

// public/bgm.(mp3|wav|m4a)가 있을 때만 깐다. 없으면 무음으로 렌더된다.
// 문제 장면(EP1~3)은 작게, 이어:잇 로고(turnAt)부터 키우고, 끝 2초에 사라진다.
export const Bgm: React.FC<{ turnAt: number; total: number }> = ({ turnAt, total }) => {
  const file = getStaticFiles().find((f) => /^bgm\.(mp3|wav|m4a)$/i.test(f.name));
  if (!file) return null;

  return (
    <Audio
      src={staticFile(file.name)}
      loop
      loopVolumeCurveBehavior="extend"
      volume={(f) =>
        interpolate(
          f,
          [0, 30, turnAt, turnAt + 45, total - 60, total],
          [0, 0.35, 0.35, 0.7, 0.7, 0],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
        )
      }
    />
  );
};
