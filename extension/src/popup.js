import { coverageState, names } from "./coverage.js";
let coverageOptions = {};
const $ = (id) => document.getElementById(id);
const send = (message) => chrome.runtime.sendMessage(message);
let activeTabId;

function render(state, supported = true, enabled = true) {
  const result = state?.result;
  const score = result?.decision.risk_score || 0;
  document.body.classList.toggle("danger", score >= 80 && enabled);
  document.body.classList.toggle("amber", score > 0 && score < 80 && enabled);
  document.body.classList.toggle("paused", !enabled);
  $("enabled").checked = enabled;
  $("protection-label").textContent = enabled ? "主動偵測中" : "防護已暫停";
  $("headline").textContent = !enabled
    ? "防護已暫停"
    : !supported
      ? "這個頁面無法檢查"
      : !result
        ? "正在查看這個頁面"
        : score >= 80
          ? "先停一下，確認來源"
          : score > 0
            ? "多確認一步，更安心"
            : result.layers?.find(l => l.layer === "L3")?.status !== "ok"
              ? "內容不足，尚無法確認"
              : "目前未發現警訊";
  $("description").textContent = !enabled
    ? "重新開啟防護，繼續守護每次瀏覽。"
    : !supported
      ? "瀏覽器設定、新分頁及商店頁面不開放內容檢查。"
      : ((result?.decision.category && result.decision.category !== "未分類") ? result.decision.category + "。" : "") + "依目前取得的資料判斷，不代表網站已確認安全。";
  try {
    $("hostname").textContent = new URL(state.url).hostname;
  } catch {
    $("hostname").textContent = supported ? "等待頁面資料" : "瀏覽器內部頁面";
  }
  $("checked").textContent =
    result?.source === "backend" ? "後端已補充" : "本機分析";
  $("signals").replaceChildren();
  $("layers").replaceChildren();
  const signals = (result?.layers || []).flatMap((layer) =>
    (layer.signals || []).map((s) => ({ ...s, layer: layer.layer })),
  );
  $("signal-count").textContent = `${signals.length} 個訊號`;
  if (!signals.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    const icon = document.createElement("span");
    icon.className = "check";
    icon.textContent = "i";
    const text = document.createElement("span");
    text.textContent = result
      ? "已取得的資料暫無規則命中。敏感操作前仍請確認網址與聯絡對象。"
      : "偵測完成後，具體原因會顯示在這裡。";
    empty.append(icon, text);
    $("signals").append(empty);
  }
  for (const signal of signals) {
    const row = document.createElement("div");
    row.className = "signal";
    const icon = document.createElement("span");
    icon.className = "signal-icon";
    icon.textContent = "!";
    const body = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = signal.detail;
    const meta = document.createElement("small");
    meta.textContent = `${signal.layer} · ${signal.grade === "observed" ? "已觀察到此現象" : "待查證的推測"}`;
    body.append(title, meta);
    row.append(icon, body);
    $("signals").append(row);
  }
  let checked = 0;
  for (const layer of result?.layers || []) {
    if (layer.status === "ok") checked++;
    const row = document.createElement("div");
    row.className = "layer-row";
    const name = document.createElement("span");
    name.textContent = (layer.layer.startsWith("L") ? layer.layer + " · " : "") + (names[layer.layer] || layer.layer);
    const status = document.createElement("span");
    const coverage = coverageState(layer, coverageOptions);
    status.textContent = coverage.label;
    row.append(name, status);
    $("layers").append(row);
    if (coverage.detail) {
      const detail = document.createElement("p");
      detail.textContent = coverage.detail;
      $("layers").append(detail);
    }
    for (const feedback of layer.feedback || []) {
      const p = document.createElement("p");
      p.textContent = feedback;
      $("layers").append(p);
    }
  }
  $("coverage").textContent = `查看檢查範圍 · ${checked} 層已取得資料`;
  $("backend-status").textContent =
    result?.backend === "incompatible"
      ? "後端拒絕新版資料格式。請重啟 Python 後端，並重新載入擴充功能。"
      : result?.backend === "rate_limited"
      ? "後端查詢頻率已達上限，請稍候一分鐘。本機檢查仍有效。"
      : result?.backend === "unavailable"
      ? "本機防護持續運作。後端未連線，進階分析暫不可用。"
      : result?.backend === "pairing_required"
        ? "後端配對碼不正確，請至設定重新連線。"
        : result?.backend === "checking"
          ? "本機檢查完成，後端正在補充分析…"
          : result?.source === "backend"
            ? "已整合後端分析；未取得資料的層仍會標示。"
            : "本機偵測持續運作；可在設定連接進階分析。";
  $("rescan").disabled = !supported || !enabled;
}
async function init() {
  try {
    const data = await send({ type: "GET_STATE" });
    if (data.error) throw Error();
    coverageOptions = data;
    activeTabId = data.tabId;
    render(data.state, data.supported, data.enabled);
    $("list-info").textContent = data.listCount
      ? `${data.listCount.toLocaleString()} 筆匯入名單 · 非即時更新`
      : "名單載入失敗 · 請重新載入擴充功能";
  } catch {
    $("headline").textContent = "暫時無法連接雷達";
    $("description").textContent = "請重新開啟這個面板或重新載入擴充功能。";
  }
}
$("settings").onclick = () => chrome.runtime.openOptionsPage();
$("enabled").onchange = async () => {
  await send({
    type: "SAVE_SETTINGS",
    settings: { enabled: $("enabled").checked },
  });
  await init();
};
for (const name of ["overview", "manual"])
  $(name + "-tab").onclick = () => {
    for (const tab of ["overview", "manual"]) {
      $(tab).hidden = tab !== name;
      $(tab + "-tab").setAttribute("aria-selected", String(tab === name));
    }
    if (name === "manual") $("url").focus();
  };
$("rescan").onclick = async () => {
  $("rescan").disabled = true;
  $("backend-status").textContent = "正在重新檢查…";
  await send({ type: "CHECK_SITE", source: "current" }).catch(() => null);
  await init();
};
$("scan-form").onsubmit = async (e) => {
  e.preventDefault();
  $("scan").disabled = true;
  $("manual-status").textContent = "正在檢查…";
  $("manual-result").replaceChildren();
  try {
    const data = await send({
      type: "CHECK_SITE",
      source: "manual",
      url: $("url").value.trim(),
    });
    if (data.error) throw Error(data.error);
    const heading = document.createElement("strong");
    const score = data.result.decision.risk_score;
    heading.textContent =
      score >= 80
        ? "建議停止前往此網址"
        : score > 0
          ? "有需查證的風險訊號"
          : "目前未命中已執行的規則";
    $("manual-result").append(heading);
    for (const reason of data.result.decision.reasons) {
      const p = document.createElement("p");
      p.textContent = reason;
      $("manual-result").append(p);
    }
    const line = document.createElement("p");
    line.textContent = data.finalUrl
      ? `HTTP 落地頁：${data.finalUrl}`
      : data.url;
    $("manual-result").append(line);
    $("manual-status").textContent =
      data.fetchStatus === "http_only_no_javascript"
        ? "已檢查 HTTP 轉址與靜態內容；未執行 JavaScript。"
        : "本機網址檢查完成；未取得落地頁內容，不代表網站安全。";
  } catch {
    $("manual-status").textContent =
      "無法檢查，請輸入完整的 http:// 或 https:// 網址。";
  } finally {
    $("scan").disabled = false;
  }
};
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "session" && changes[`tab:${activeTabId}`]?.newValue)
    render(changes[`tab:${activeTabId}`].newValue, true, $("enabled").checked);
});
void init();
