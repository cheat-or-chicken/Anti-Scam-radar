import { build } from "esbuild";
import { copyFile } from "node:fs/promises";
for (const name of ["background", "content", "popup", "options", "warning"]) {
  await build({
    entryPoints: [`src/${name}.js`],
    outfile: `${name}.js`,
    bundle: true,
    format: "iife",
    target: "chrome120",
    legalComments: "none",
  });
}
await copyFile("../script/data/blocklist.json", "blocklist.json");
console.log("Built extension: local PSL + shared blocklist + UI.");
