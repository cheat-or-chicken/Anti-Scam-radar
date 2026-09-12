import { test } from "node:test";
import assert from "node:assert/strict";
import {
  analyzeLocal,
  checkBlocklist,
  skeleton,
  parseURL,
  trusted,
  sameSite,
  mergeAnalysis,
} from "../src/core.js";
const data = {
  domains: {
    "pages.dev": { s: ["NPA"] },
    "bad.pages.dev": { s: ["NPA"] },
    "evil.example.com": { s: ["NPA"] },
  },
  digitSkeletons: { "pay#.com": ["pay1.com", "pay2.com"] },
};
test("private PSL boundary prevents collateral blocking", () => {
  assert.equal(checkBlocklist("https://good.pages.dev", data).kind, "none");
  assert.equal(checkBlocklist("https://a.bad.pages.dev", data).kind, "listed");
  assert.equal(sameSite("https://a.vercel.app", "https://b.vercel.app"), false);
});
test("numeric variants are weak and numeric-only labels excluded", () => {
  assert.equal(checkBlocklist("https://pay3.com", data).kind, "similar");
  assert.equal(skeleton("123.com"), null);
  assert.equal(
    analyzeLocal({ url: "https://pay3.com" }, data).decision.display_level,
    "banner",
  );
});
test("hostname suffix spoof is not government trust", () => {
  assert.equal(trusted("https://mvdis.gov.tw.evil.com"), false);
  assert.equal(trusted("https://www.mvdis.gov.tw"), true);
  assert.equal(trusted("http://www.mvdis.gov.tw"), false);
});
test("URL validation blocks credentials and non-web schemes", () => {
  for (const url of [
    "file:///tmp/secret",
    "https://u:p@x.com",
    "https://x.com:9000",
    "https://x.com\n",
  ])
    assert.throws(() => parseURL(url));
});
test("normal OTP and warning texts do not trigger", () => {
  const r = analyzeLocal(
    {
      url: "https://shop.com",
      text: "請輸入OTP登入。請勿安裝 AnyDesk。",
      sensitive_fields: ["otp"],
    },
    data,
  );
  assert.equal(r.decision.risk_score, 0);
});
test("government impersonation + pressure prompts warning", () => {
  const r = analyzeLocal(
    { url: "https://fake.com", title: "監理服務網", text: "罰單請立即繳納" },
    data,
  );
  assert.equal(r.decision.display_level, "banner");
  assert.ok(r.decision.interrupt_triggers.includes("submit"));
});
test("imported blocklist stops listed site", () => {
  const r = analyzeLocal({ url: "https://evil.example.com" }, data);
  assert.equal(r.decision.display_level, "block");
});
test("missing database never looks like a successful list check", () => {
  const r = analyzeLocal({ url: "https://example.com" }, null);
  assert.equal(r.listReady, false);
  assert.equal(r.layers.find((l) => l.layer === "BLOCKLIST").status, "error");
});
test("backend cannot erase local evidence", () => {
  const url = "https://fake.com";
  const local = analyzeLocal({ url, title: "監理服務網" }, data);
  const r = mergeAnalysis(url, local, { layers: [] });
  assert.equal(r.decision.risk_score, local.decision.risk_score);
});

test("FETC transposition plus serial warns without content and never hard blocks", () => {
  const result = analyzeLocal({ url: "https://ftec-08.twietio.vip/" }, null);
  assert.equal(result.decision.display_level, "banner");
  assert.equal(result.decision.risk_score, 35);
  assert.equal(result.layers.find(l => l.layer === "L3").status, "missing");
  assert.ok(result.decision.reasons[0].includes("fetc.net.tw"));
});

test("FETC official and unrelated numbered subdomains do not trigger brand pattern", () => {
  for (const url of ["https://www.fetc.net.tw/", "https://css.fetc.net.tw/", "https://shop-08.example.com/", "https://fetcetera.example.com/"]) {
    const result = analyzeLocal({ url }, null);
    assert.ok(!result.layers.flatMap(l => l.signals).some(s => s.id === "brand_lookalike_fetc"));
  }
});

test("demo port permits only fixed loopback, never arbitrary remote ports", () => {
  assert.equal(parseURL("http://127.0.0.1:8088/traffic.html").port, "8088");
  for (const url of ["http://example.com:8088/", "http://127.0.0.1:8089/", "https://127.0.0.1:8088/"])
    assert.throws(() => parseURL(url));
});

test('new Google and screenshot layers survive merge and affect the verdict', () => {
  const local = analyzeLocal({url:'https://example.com'}, null);
  const remote = {layers:[
    {layer:'VISION',status:'ok',signals:[{id:'visual',detail:'画面冒用品牌',weight:10}]},
    {layer:'GOOGLE_URL_REPUTATION',status:'ok',signals:[{id:'google_match',detail:'Google 回報威脅',weight:35}]}
  ]};
  const merged = mergeAnalysis('https://example.com', local, remote);
  assert.ok(merged.layers.some(l => l.layer === 'VISION'));
  assert.ok(merged.layers.some(l => l.layer === 'GOOGLE_URL_REPUTATION'));
  assert.equal(merged.decision.risk_score,45);
  assert.equal(merged.decision.reasons.length,2);
});
