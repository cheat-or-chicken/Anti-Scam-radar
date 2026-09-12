// Real MV3 browser integration. All target pages are local route fixtures; no suspicious sites visited.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { spawn } from "node:child_process";
const root = resolve("..");
const profile = await mkdtemp(join(tmpdir(), "radar-browser-"));
const config = join(profile, "settings.json");
await writeFile(
  config,
  JSON.stringify({
    audit_enabled: false,
    llm_enabled: false,
    network_enabled: false,
  }),
);
await mkdir("artifacts", { recursive: true });
let occupied = false;
try { occupied = (await fetch("http://127.0.0.1:8765/health")).ok; } catch {}
if (occupied) {
  await rm(profile, { recursive: true, force: true });
  throw Error("Port 8765 already has a backend. Stop it before browser tests; do not test an unrelated or outdated server.");
}
const backend = spawn(
  resolve(root, ".venv/bin/python"),
  ["-m", "script.server", "--config", config],
  { cwd: root, stdio: "pipe" },
);
let context;
let backendError = "";
backend.stderr.on("data", (chunk) => {
  backendError += chunk.toString();
});
try {
  for (let i = 0; i < 50; i++) {
    try {
      if ((await fetch("http://127.0.0.1:8765/health")).ok) break;
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  assert.equal(backend.exitCode, null, backendError);
  assert.ok(
    (await fetch("http://127.0.0.1:8765/health")).ok,
    "backend not ready",
  );
  context = await chromium.launchPersistentContext(profile, {
    channel: "chromium",
    headless: true,
    args: [
      `--disable-extensions-except=${resolve(".")}`,
      `--load-extension=${resolve(".")}`,
    ],
    viewport: { width: 1180, height: 820 },
  });
  let [worker] = context.serviceWorkers();
  if (!worker) worker = await context.waitForEvent("serviceworker");
  const id = new URL(worker.url()).hostname;
  const errors = [];
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  const simple =
    '<!doctype html><title>小日子書店</title><h1>慢慢選一本好書</h1><p>新書與閱讀日常</p><input type="password" value="PRIVATE_INPUT_VALUE">';
  await context.route("https://**.example/**", (route) =>
    route.fulfill({ contentType: "text/html", body: simple }),
  );
  await page.goto("https://bookshop.example/");
  async function stateFor(target) {
    return worker.evaluate(async (url) => {
      const [tab] = await chrome.tabs.query({ url });
      const state = await chrome.storage.session.get(`tab:${tab.id}`);
      return state[`tab:${tab.id}`];
    }, target);
  }
  async function until(fn, label, timeout = 15000) {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const value = await fn();
      if (value) return value;
      await new Promise((r) => setTimeout(r, 100));
    }
    throw Error("Timed out: " + label);
  }
  const normal = await until(async () => {
    const s = await stateFor("https://bookshop.example/");
    return s?.result.layers[2].status === "ok" && s;
  }, "normal snapshot");
  assert.equal(normal.result.decision.risk_score, 0);
  assert.ok(!JSON.stringify(normal).includes("PRIVATE_INPUT_VALUE"));
  console.log(
    "PASS: automatic normal-page analysis and no input values stored",
  );
  // Background restarted state remains persisted in chrome.storage.session.
  const tab = await context.newPage();
  await tab.goto(`chrome-extension://${id}/popup.html`);
  await tab.screenshot({ path: "artifacts/popup-browser-page.png" });
  await page.bringToFront();
  // Open popup as an extension page but force active tab query to the actual target for UI verification.
  await tab.evaluate(async () => {
    const [target] = await chrome.tabs.query({
      url: "https://bookshop.example/*",
    });
    await chrome.tabs.update(target.id, { active: true });
  });
  await tab.reload();
  await until(
    () =>
      tab
        .locator("#headline")
        .textContent()
        .then((t) => t === "目前未發現警訊"),
    "popup ready",
  );
  await tab.setViewportSize({ width: 420, height: 650 });
  await tab.screenshot({ path: "artifacts/popup-normal.png", fullPage: true });
  await tab.locator("#manual-tab").click();
  await tab.locator("#url").fill("https://mvdis.gov.tw.fake.example/notice");
  await tab.locator("#scan").click();
  await until(
    () =>
      tab
        .locator("#manual-result")
        .textContent()
        .then((t) => t.includes("查證")),
    "manual result",
  );
  console.log("PASS: popup reads current tab and manual URL check");
  // Actual on-page automatic detection and sensitive focus protection.
  await page.goto("https://fraud-demo.example/");
  await page.evaluate(() => {
    document.title = "監理服務網";
    document.body.innerHTML =
      '<h1>監理服務網</h1><p>罰單請立即繳納</p><input type="password" id="password">';
  });
  const suspicious = await until(async () => {
    const s = await stateFor("https://fraud-demo.example/");
    return s?.result.decision.risk_score >= 60 && s;
  }, "DOM mutation reanalysis");
  assert.equal(suspicious.result.decision.display_level, "banner");
  await page.locator("#password").focus();
  await until(
    () => page.locator("#anti-scam-radar-overlay").count(),
    "sensitive guard",
  );
  await page.screenshot({ path: "artifacts/sensitive-guard.png" });
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#password").inputValue(), "");
  console.log("PASS: mutation observer + sensitive input interruption");
  // Unknown page cannot send privileged extension UI commands.
  const unauthorized = await page.evaluate(async () => {
    // Web pages have no extension runtime; this verifies the isolated-world boundary from page JS.
    return typeof chrome.runtime?.sendMessage;
  });
  assert.equal(unauthorized, "undefined");
  // Options are real extension UI, pair with test backend (no OpenAI enabled).
  const options = await context.newPage();
  await options.goto(`chrome-extension://${id}/options.html`);
  const token = (
    await readFile(join(root, "var/extension-token.txt"), "utf8")
  ).trim();
  await options.locator("#pairingToken").fill(token);
  await options.locator("#backendEnabled").check();
  await options.locator("#test").click();
  await until(
    () =>
      options
        .locator("#status")
        .textContent()
        .then((t) => t.includes("連線成功")),
    "backend pairing",
  );
  // Don't include pairing secrets in screenshots.
  await options.locator("#pairingToken").fill("");
  await options.screenshot({ path: "artifacts/options.png", fullPage: true });
  await page.goto("https://integrated.example/");
  await until(
    async () =>
      (await stateFor("https://integrated.example/"))?.result.source ===
      "backend",
    "backend enrichment",
  );
  console.log("PASS: authenticated extension → Python pipeline integration");
  const beforeRepeat = await stateFor("https://integrated.example/");
  await worker.evaluate(async () => {
    const [target] = await chrome.tabs.query({ url: "https://integrated.example/" });
    await chrome.tabs.sendMessage(target.id, { type: "RADAR_RESCAN", force: true });
  });
  const afterRepeat = await stateFor("https://integrated.example/");
  assert.equal(afterRepeat.result.source, "backend");
  assert.equal(afterRepeat.jobId, beforeRepeat.jobId);
  console.log("PASS: repeated snapshot retains completed backend layers");
  // Mock this reported host: do not load or execute the real site's scripts.
  await context.route("https://ftec-08.twietio.vip/**", route => route.fulfill({
    status: 404, contentType: "text/html", body: "<h1>404 Not Found</h1>"
  }));
  await page.goto("https://ftec-08.twietio.vip/");
  const lookalike = await until(async () => {
    const s = await stateFor("https://ftec-08.twietio.vip/");
    return s?.result.decision.display_level === "banner" && s;
  }, "FETC lookalike banner without page content");
  assert.ok(lookalike.result.decision.reasons.some(r => r.includes("fetc.net.tw")));
  assert.notEqual(lookalike.result.decision.display_level, "block");
  console.log("PASS: reported FETC lookalike warns even on a 404 fixture");
  // Real listed-domain intercept without visiting the site: all response traffic is mocked.
  const list = JSON.parse(await readFile("blocklist.json", "utf8"));
  const listed = Object.keys(list.domains).find((h) => h === "www.0857.games");
  assert.ok(listed);
  await context.route("https://www.0857.games/**", (route) =>
    route.fulfill({ contentType: "text/html", body: "<h1>Fixture only</h1>" }),
  );
  await page.goto("https://www.0857.games/").catch(() => {});
  await until(() => page.url().includes("/warning.html"), "warning redirect");
  await until(() => page.locator("#proceedBtn").isEnabled(), "warning data");
  await page.screenshot({ path: "artifacts/warning.png", fullPage: true });
  await page.locator("#proceedBtn").click();
  await until(
    () => page.url() === "https://www.0857.games/",
    "one-site bypass",
  );
  console.log("PASS: blocklist interstitial and same-tab explicit bypass");
  assert.deepEqual(errors, []);
  console.log(
    "Browser integration passed. Screenshots in extension/artifacts/.",
  );
} finally {
  await context?.close();
  backend.kill("SIGTERM");
  await rm(profile, { recursive: true, force: true });
}
