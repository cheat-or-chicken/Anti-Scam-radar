# 各層資料與狀態修正

本次發現的不只是顯示文案問題：本機版漏做部分檢查、後端自動路由停用全部網路、快照重掃覆蓋後端結果、前後端 timeout 不一致，以及舊後端仍占用 8765 拒絕新版欄位，都會造成各層長期沒有資料。

已修正：

- L4、L15：content script 明確回報已採集 DOM；沒有外部表單或隱藏指令時，表示限定範圍已檢查，不再混同尚未取得快照。這不證明已監控敏感資料外傳。
- L5：後端允許 network_enabled 時，自動對主網域查 RDAP，單次上限 8 秒，結果／失敗快取 5 分鐘、最多 256 網域。客戶端提供的註冊日期仍會清除。失敗不影響其餘層。
- L8：同一 documentId 與完整網址下保存上一份欄位種類，DOM 變動後比較。不保存欄位值，不是跨日網頁歷史。
- L9：本機新增與 Python 對齊的用詞規則；只有弱風險分。
- L11：採集關於／聯絡資訊連結。找到連結只表示存在此類入口，不認證其內容或公司身分；沒找到仍不武斷宣稱沒有經營資訊。
- L7：後端 AI／上傳未啟用時回 skipped 與明確原因；仍只審查取得的 inline JS，不執行程式。
- snapshot 以內容摘要識別同一頁的一致快照，在 60 秒內保留既有結果和進行中的工作，不再覆蓋後端來源。摘要不含配對碼；設定變更會清除摘要。實際內容變動會重新分析，仍受後端 12 次／分鐘限制。
- 後端連線等待延長至 140 秒，涵蓋手動 HTTP 抓取與 LLM；429 顯示頻率限制，422 明確提示重啟／檢查版本，而非只說沒有資料。
- `coverage.js` 將呈現狀態與證據 verdict 分開：AI 未啟用、後端未啟用、首次基準、等待下載、沒有 QR 解碼資料、需額外裝置探測都有具體說明。沒有以假資料填滿所有層。

新增檔案：`extension/src/coverage.js`（層名稱／等待原因）、`extension/tests/coverage.test.js`（本機資料與呈現狀態測試）。其他修改在 content/background/core/popup/api、Python models/server/rules 及既有回歸測試。

瀏覽器測試新增重掃保留後端結果驗證。測試開始前會拒絕已占用 8765 的環境，避免把使用者啟動的舊後端當成本次測試服務；不會自動關閉未知服務。

要套用修改，需要重新啟動後端與在 Chrome 擴充功能管理頁按「重新載入」，再刷新原網頁。L6（額外裝置探測）、L12（下載事件）、L13（QR 解碼輸入）與首次 L8 仍是條件式檢查，不應全部顯示已完成。

## 執行進度 log

`uv run python -m script.server` 啟動時會把進度寫到終端機與 `var/backend.log`。可用 `tail -f var/backend.log` 即時追蹤，或透過 `--log-file` 指定路徑。日誌單檔上限約 2 MB、保留 3 份輪替備份，`var/` 不提交 Git。

`request` 是後端產生的隨機請求識別碼，也會放在 `X-Request-ID` 回應標頭。`stage` 區分各層 rules、RDAP、LLM、BLOCKLIST、adjudication；`status` 為 started/finished/failed 或實際層狀態；`elapsed_ms` 是毫秒耗時。finished 只表示該階段返回，不表示網站安全；failed/unknown/缺少資料仍須看後續結果。

不記錄 API key、配對碼、待查 URL、網頁文字或 SDK 錯誤本文。`script/progress.py` 提供 ContextVar 請求關聯、階段計時及輪替日誌；`tests/test_progress.py` 驗證階段與 HTTP 狀態存在、敏感資料不進入日誌。服務的 Uvicorn 啟停訊息仍在終端機。
