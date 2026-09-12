import test from "node:test";
import assert from "node:assert/strict";
import { coverageState } from "../src/coverage.js";
import { analyzeLocal } from "../src/core.js";

test("conditional checks explain why they wait, not generic missing data", () => {
  assert.equal(coverageState({ layer: "L12", status: "missing" }).label, "等待下載事件");
  assert.equal(coverageState({ layer: "L7", status: "missing" }).label, "AI 未啟用");
  assert.equal(coverageState({ layer: "L5", status: "missing" }).label, "後端未啟用");
});
test("DOM checks and previous field baseline supply real local layers", () => {
  const r = analyzeLocal({ url: "https://example.com", text: "正常內容", dom_collected: true,
    missing_business_pages: false, previous_sensitive_fields: [], sensitive_fields: ["otp"] }, null);
  for (const n of [4, 8, 9, 11, 15]) assert.equal(r.layers[n].status, "ok");
  assert.ok(r.layers[8].signals.some(s => s.id === "new_sensitive_form"));
  assert.equal(r.layers[13].status, "missing");
});
