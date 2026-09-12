const button = document.querySelector("#analyze");
const status = document.querySelector("#status");
const result = document.querySelector("#result");
const score = document.querySelector("#score");
const summary = document.querySelector("#summary");
const reasons = document.querySelector("#reasons");
const meta = document.querySelector("#meta");

function showResult(analysis) {
  const decision = analysis.decision || {};
  score.textContent = `風險分數：${decision.risk_score ?? "—"}／100`;
  summary.textContent = `顯示等級：${decision.display_level || "unknown"}`;
  reasons.replaceChildren();
  for (const reason of decision.reasons || []) {
    const item = document.createElement("li");
    item.textContent = reason;
    reasons.append(item);
  }
  const vision = (analysis.layers || []).find((layer) => layer.layer === "VISION");
  meta.textContent = `LLM 呼叫：${analysis.llm_calls ?? 0}${vision ? `；截圖分析：${vision.status}` : ""}`;
  const google = (analysis.layers || []).find((layer) => layer.layer === "GOOGLE_URL_REPUTATION");
  if (google) meta.textContent += `；Google URL 信譽：${google.status}`;
  result.hidden = false;
}

button.addEventListener("click", async () => {
  button.disabled = true;
  result.hidden = true;
  status.textContent = "正在擷取畫面並分析…";
  try {
    const response = await chrome.runtime.sendMessage({ type: "analyze-current-tab" });
    if (!response?.ok) throw new Error(response?.error || "分析失敗。");
    showResult(response.result);
    status.textContent = "分析完成。";
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : "分析失敗。";
  } finally {
    button.disabled = false;
  }
});
