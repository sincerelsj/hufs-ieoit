import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Caption } from "../components/Caption";
import { Panel } from "../components/Panel";
import { ProblemStage } from "../components/ProblemStage";
import { clamp, inOut, out } from "../theme";

// EP.2 전설의 조교 — 3컷(텅 빈 인수인계 서랍)에 머물고, 끝에 4컷(학교가 펑)을 짧게 터뜨린다.
export const Ep2: React.FC = () => {
  const frame = useCurrentFrame();
  const boom = 165;

  // 펑! 직후 0.5초 동안 흔들림
  const shake = interpolate(frame, [boom, boom + 15], [24, 0], clamp);
  const shakeX = Math.sin(frame * 2.3) * shake;
  const shakeY = Math.cos(frame * 3.1) * shake * 0.6;

  return (
    <ProblemStage ep="EP.2 전설의 조교">
      <Panel
        src="webtoon/ep2-3.png"
        width={900}
        zoom={interpolate(frame, [0, boom], [1, 1.08], { ...clamp, easing: inOut })}
        focus="50% 0%"
        style={{
          position: "absolute",
          left: 110,
          top: 131,
          opacity: interpolate(frame, [0, 14, boom - 4, boom], [0, 1, 1, 0], clamp),
          scale: interpolate(frame, [0, 22], [0.94, 1], { ...clamp, easing: out }),
        }}
      />
      <Caption
        kicker="문제 ② 끊기는 인수인계"
        lines={["임기가 끝나면", "노하우도 사라진다"]}
        from={20}
        to={boom - 10}
        style={{ position: "absolute", left: 1110, top: 360 }}
      />

      <AbsoluteFill
        name="Boom"
        style={{
          justifyContent: "center",
          alignItems: "center",
          opacity: interpolate(frame, [boom, boom + 3], [0, 1], clamp),
          translate: `${shakeX}px ${shakeY}px`,
        }}
      >
        <Panel
          src="webtoon/ep2-4.png"
          width={1040}
          zoom={interpolate(frame, [boom, boom + 75], [1.15, 1], { ...clamp, easing: out })}
          style={{
            scale: interpolate(frame, [boom, boom + 10], [1.25, 1], { ...clamp, easing: out }),
          }}
        />
      </AbsoluteFill>
      <AbsoluteFill
        name="Flash"
        style={{
          background: "white",
          opacity: interpolate(frame, [boom - 1, boom, boom + 8], [0, 0.9, 0], clamp),
        }}
      />
    </ProblemStage>
  );
};
