import { Easing } from "remotion";
import { loadFont } from "@remotion/google-fonts/NotoSansKR";

export const { fontFamily } = loadFont("normal", {
  weights: ["400", "500", "700", "900"],
  subsets: ["korean", "latin"],
  ignoreTooManyRequestsWarning: true,
});

// 연감 서가(A안) 색을 그대로 쓴다.
export const C = {
  night: "#12233a",
  nightField: "#1b3150",
  nightInk: "#e7ecf3",
  nightMuted: "#b8c3d3",
  page: "#fbfaf8",
  pageLine: "#e3e0da",
  ink: "#142033",
  muted: "#5b677a",
  accent: "#1f5f8b",
  thread: "#e7b53a",
  threadInk: "#b07d12",
  wood: "#6b4a2b",
  woodDark: "#3f2b18",
  alert: "#e2574c",
};

export const FPS = 30;
export const W = 1920;
export const H = 1080;

export const out = Easing.bezier(0.16, 1, 0.3, 1);
export const inOut = Easing.bezier(0.65, 0, 0.35, 1);
export const clamp = {
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
} as const;
