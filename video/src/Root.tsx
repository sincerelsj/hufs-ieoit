import { Composition, Folder } from "remotion";
import { IeoitVideo, SCENES, TOTAL } from "./IeoitVideo";
import { FPS, H, W } from "./theme";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="IeoitPrototype"
        component={IeoitVideo}
        durationInFrames={TOTAL}
        fps={FPS}
        width={W}
        height={H}
      />
      <Folder name="Scenes">
        {Object.entries(SCENES).map(([id, s]) => (
          <Composition
            key={id}
            id={id}
            component={s.component}
            durationInFrames={s.duration}
            fps={FPS}
            width={W}
            height={H}
          />
        ))}
      </Folder>
    </>
  );
};
