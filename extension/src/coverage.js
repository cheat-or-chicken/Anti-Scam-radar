// Presentation state is separate from the evidence verdict: waiting does not mean clean.
export const names = {
  L0: "檢查分流", L1: "網址與品牌近似", L2: "品牌與網域一致性", L3: "詐騙話術",
  L4: "表單與程式線索", L5: "網域註冊資料", L6: "不同裝置內容比較", L7: "AI 靜態程式審查",
  L8: "本分頁欄位變化", L9: "語言用詞", L10: "人工複核文字指紋", L11: "經營資訊連結",
  L12: "下載檔案", L13: "QR code", L14: "敏感操作提醒", L15: "隱藏指令與延遲欄位",
  L16: "本機回報資料", BLOCKLIST: "通報名單", WORKFLOW: "AI 情境與證據判斷", VISION: "截圖 AI 分析", GOOGLE_URL_REPUTATION: "Google 網址信譽"
};
export function coverageState(layer, options = {}) {
  if (layer.status === "ok") return { label: "已檢查", detail: layer.layer === "L4" ? "涵蓋靜態表單／程式線索，不代表已監測實際資料外傳。" : "" };
  if (layer.status === "error") return { label: "查詢未完成", detail: layer.user_facing_reason || "請稍後重新檢查。" };
  const reasons = {
    L2: ["缺少標題", "頁面尚未提供可辨識的標題或品牌宣稱。"],
    L3: ["缺少可讀內容", "空白、錯誤或驗證頁無法用來排除詐騙話術。"],
    L4: ["等待頁面快照", "重新整理頁面以取得表單結構；不採集輸入值。"],
    L5: ["需要後端查詢", "開啟本機後端及 network_enabled 後自動查 RDAP；查不到不等於安全。"],
    L6: ["需額外探測", "此頁快照只有一種裝置；未自動另開多裝置連線。"],
    L7: ["沒有可審查片段", "僅分析已取得的 inline JavaScript；外部腳本尚未下載，且不執行 JS。"],
    L8: ["建立比對基準", "首次快照沒有歷史；本分頁內容變更後自動比較欄位種類。"],
    L9: ["缺少可讀文字", "頁面尚未提供可分析的文字。"],
    L10: ["需要本機資料庫", "連接後端才會查詢人工複核文字指紋。"],
    L11: ["尚無經營資訊佐證", "未找到可辨識的關於／聯絡連結；不代表商家不存在。"],
    L12: ["等待下載事件", "出現可辨識下載時才檢查檔名與來源，並非檢查失敗。"],
    L13: ["尚無 QR 資料", "未啟用圖片 QR 解碼；不能宣稱頁面沒有 QR code。"],
    L15: ["等待 DOM 檢查", "重新整理頁面後會檢查可見的隱藏標記與欄位變化。"],
    L16: ["需要本機資料庫", "連接後端以查詢本機去重回報，不是全球即時社群資料。"]
  };
  if (layer.layer === "L7" && !options.llmEnabled)
    return { label: "AI 未啟用", detail: "請在擴充功能設定啟用 AI，並確認後端允許 LLM 與內容上傳。" };
  if (["L5", "L7", "L10", "L16"].includes(layer.layer) && !options.backendEnabled)
    return { label: "後端未啟用", detail: "啟動 Python 服務，在擴充功能設定開啟本機後端並完成配對。" };
  if (layer.status === "skipped") return { label: "尚未啟用", detail: layer.user_facing_reason };
  const [label, detail] = reasons[layer.layer] || ["尚未完成", layer.user_facing_reason];
  return { label, detail };
}
