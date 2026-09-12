// Rasterize the project's vector toolbar icon; no network or generated artwork.
import { chromium } from "playwright";
import { readFile, writeFile } from "node:fs/promises";
const svg = await readFile("icons/radar.svg", "utf8");
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  for (const size of [16, 32, 48, 128]) {
    const png = await page.evaluate(
      async ({ svg, size }) => {
        const blob = new Blob([svg], { type: "image/svg+xml" });
        const url = URL.createObjectURL(blob);
        const img = new Image();
        img.src = url;
        await img.decode();
        const canvas = document.createElement("canvas");
        canvas.width = size;
        canvas.height = size;
        canvas.getContext("2d").drawImage(img, 0, 0, size, size);
        URL.revokeObjectURL(url);
        return canvas.toDataURL("image/png").split(",")[1];
      },
      { svg, size },
    );
    await writeFile(`icons/radar-${size}.png`, Buffer.from(png, "base64"));
  }
} finally {
  await browser.close();
}
