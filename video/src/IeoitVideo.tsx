import React from "react";
import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { Bgm } from "./components/Bgm";
import { Ep1 } from "./scenes/Ep1";
import { Ep2 } from "./scenes/Ep2";
import { Ep3 } from "./scenes/Ep3";
import { Gather } from "./scenes/Gather";
import { Hook } from "./scenes/Hook";
import { KeepPosting } from "./scenes/KeepPosting";
import { Outro } from "./scenes/Outro";
import { Turn } from "./scenes/Turn";
import { Yearbook } from "./scenes/Yearbook";

// 장면 길이(프레임, 30fps). Root.tsx의 개별 컴포지션 길이도 이 값을 쓴다.
export const SCENES = {
  Hook: { component: Hook, duration: 90 },
  Ep1: { component: Ep1, duration: 270 },
  Ep2: { component: Ep2, duration: 240 },
  Ep3: { component: Ep3, duration: 360 },
  Turn: { component: Turn, duration: 120 },
  KeepPosting: { component: KeepPosting, duration: 180 },
  Gather: { component: Gather, duration: 180 },
  Yearbook: { component: Yearbook, duration: 210 },
  Outro: { component: Outro, duration: 150 },
} as const;

const FADE = 15;
const order = Object.keys(SCENES) as (keyof typeof SCENES)[];

export const TOTAL =
  order.reduce((sum, k) => sum + SCENES[k].duration, 0) -
  FADE * (order.length - 1);

// Turn 장면이 시작하는 프레임 (앞 장면 길이 합 - 겹치는 페이드)
const TURN_AT =
  order
    .slice(0, order.indexOf("Turn"))
    .reduce((sum, k) => sum + SCENES[k].duration, 0) -
  FADE * order.indexOf("Turn");

export const IeoitVideo: React.FC = () => (
  <>
    <Bgm turnAt={TURN_AT} total={TOTAL} />
    <TransitionSeries>
      {order.flatMap((k, i) => {
        const { component: Scene, duration } = SCENES[k];
        const seq = (
          <TransitionSeries.Sequence
            key={k}
            name={k}
            durationInFrames={duration}
          >
            <Scene />
          </TransitionSeries.Sequence>
        );
        return i === 0
          ? [seq]
          : [
              <TransitionSeries.Transition
                key={`${k}-in`}
                presentation={fade()}
                timing={linearTiming({ durationInFrames: FADE })}
              />,
              seq,
            ];
      })}
    </TransitionSeries>
  </>
);
