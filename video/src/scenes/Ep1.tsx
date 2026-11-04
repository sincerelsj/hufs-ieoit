import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Caption } from "../components/Caption";
import { Panel } from "../components/Panel";
import { ProblemStage } from "../components/ProblemStage";
import { clamp, inOut, out } from "../theme";

// EP.1 사라진 추억 — 즐거웠던 1·2컷을 빠르게 보여 주고, 3컷(아무리 내려도 기록이 안 나옴)에 머문다.
export const Ep1: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <ProblemStage ep="EP.1 사라진 추억">
      <AbsoluteFill
        name="Memories"
        style={{
          flexDirection: "row",
          justifyContent: "center",
          alignItems: "center",
          gap: 60,
          opacity: interpolate(frame, [72, 86], [1, 0], clamp),
        }}
      >
        <Panel
          src="webtoon/ep1-1.png"
          width={760}
          zoom={interpolate(frame, [0, 86], [1, 1.06], clamp)}
          style={{
            opacity: interpolate(frame, [0, 12], [0, 1], clamp),
            translate: interpolate(frame, [0, 24], ["0px 60px", "0px 0px"], { ...clamp, easing: out }),
            rotate: "-1.5deg",
          }}
        />
        <Panel
          src="webtoon/ep1-2.png"
          width={760}
          zoom={interpolate(frame, [0, 86], [1, 1.06], clamp)}
          style={{
            opacity: interpolate(frame, [16, 28], [0, 1], clamp),
            translate: interpolate(frame, [16, 40], ["0px 60px", "0px 0px"], { ...clamp, easing: out }),
            rotate: "1.5deg",
          }}
        />
      </AbsoluteFill>

      <Panel
        src="webtoon/ep1-3.png"
        width={900}
        zoom={interpolate(frame, [80, 270], [1, 1.08], { ...clamp, easing: inOut })}
        focus="50% 0%"
        style={{
          position: "absolute",
          left: 110,
          top: 131,
          opacity: interpolate(frame, [78, 94], [0, 1], clamp),
          scale: interpolate(frame, [78, 100], [0.94, 1], { ...clamp, easing: out }),
        }}
      />
      <Caption
        kicker="문제 ① 찾을 수 없는 기록"
        lines={["피드에 묻힌 기록은", "다시 찾을 수 없다"]}
        from={100}
        style={{ position: "absolute", left: 1110, top: 360 }}
      />
    </ProblemStage>
  );
};
