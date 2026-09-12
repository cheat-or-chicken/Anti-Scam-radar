// Compatibility entry point. The maintained importer now lives in script/build_blocklist.py.
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("../", import.meta.url));
const r = spawnSync("uv", ["run", "python", "-m", "script.build_blocklist"], {
  cwd: root,
  stdio: "inherit",
});
process.exit(r.status ?? 1);
