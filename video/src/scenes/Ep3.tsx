import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { Caption } from "../components/Caption";
import { Panel } from "../components/Panel";
import { ProblemStage } from "../components/ProblemStage";
import { clamp, out } from "../theme";

// EP.3 놓쳐버린 공지 — 네 컷을 차례로 크게 보여 준다.
const CUTS = [
  { src: "webtoon/ep3-1.png", from: 0, to: 50, focus: "50% 0%" },
  { src: "webtoon/ep3-2.png", from: 50, to: 150, focus: "50% 0%" },
  { src: "webtoon/ep3-3.png", from: 150, to: 245, focus: "50% 0%" },
  { src: "webtoon/ep3-4.png", from: 245, to: 380, focus: "50% 0%" },
];

export const Ep3: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <ProblemStage ep="EP.3 놓쳐버린 공지">
      {CUTS.map((c) => (
        <Panel
          key={c.src}
          src={c.src}
          width={900}
          zoom={interpolate(frame, [c.from, c.to], [1, 1.1], clamp)}
          focus={c.focus}
          style={{
            position: "absolute",
            left: 110,
            top: 131,
            opacity: interpolate(frame, [c.from, c.from + 10, c.to - 2, c.to + 8], [0, 1, 1, 0], clamp),
            translate: interpolate(frame, [c.from, c.from + 20], ["40px 0px", "0px 0px"], {
              ...clamp,
              easing: out,
            }),
          }}
        />
      ))}
      <Caption
        kicker="문제 ③ 흩어진 정보"
        lines={["학생회·학과·동아리", "계정만 161곳"]}
        from={60}
        to={235}
        style={{ position: "absolute", left: 1110, top: 360 }}
      />
      <Caption
        kicker="문제 ③ 흩어진 정보"
        lines={["흩어진 공지는", "결국 놓친다"]}
        from={250}
        style={{ position: "absolute", left: 1110, top: 360 }}
      />
    </ProblemStage>
  );
};
