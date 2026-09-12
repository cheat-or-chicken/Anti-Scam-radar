# 雙層文字遮罩與可選截圖

截圖預設開啟，使用者可在設定關閉；不因輸入欄位或個資文字自動拒絕截圖。本次僅處理文字資料，不恢復先前的截圖攔截或 Google 根網址限制。

- `script/data/privacy_patterns.json`：前後端共用 email、台灣身分證、電話／長數字、密碼賦值、Bearer token、常見 API key 模式。
- `extension/src/privacy.js`、`src/api.js`：集中在 HTTP 呼叫前遮罩 context 的 title、text、html、hidden_text、claimed_brand、scripts、probe_texts、qr_payloads。原本瀏覽器本機分析資料不改動。
- `script/privacy.py`、`script/llm.py`：在原有語意入口遮罩，以及 Responses API 最終 input 出口再遮罩一次；JSON 結構保留，指定密鑰欄位值直接取代。API 認證 key／配對碼不屬於被分析文字，不改動。
- 截圖 base64 不修改，也沒有 OCR 遮罩。完整導航 URL 和必要的網址列表仍保留供查核；URL 中的個資不在本次文字欄位遮罩範圍。

此功能是規則式、盡力而為的遮罩，不是保證去識別；姓名、地址、未支援格式或圖片內個資仍可能傳送。使用者關閉截圖可避免畫面上傳；文字分析仍受其後端／AI 開關控制。

驗證：Node 傳送前遮罩、Python SDK 呼叫參數遮罩、Chromium 真實截圖保留且 HTTP 文字 email／電話已遮罩，以及關閉截圖後文字分析繼續。
