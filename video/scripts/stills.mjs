// 확인용 정지 화면 렌더: node scripts/stills.mjs <출력폴더> <프레임...>
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import path from "node:path";

const [outDir, ...frames] = process.argv.slice(2);
const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts") });
const composition = await selectComposition({ serveUrl, id: "IeoitPrototype" });
for (const f of frames) {
  await renderStill({
    serveUrl,
    composition,
    frame: Number(f),
    output: path.join(outDir, `f${String(f).padStart(4, "0")}.jpg`),
    imageFormat: "jpeg",
    jpegQuality: 70,
    scale: 0.5,
  });
  console.log("rendered", f);
}
