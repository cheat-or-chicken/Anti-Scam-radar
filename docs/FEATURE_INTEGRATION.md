# 截圖與 Google 功能整合

已整合遠端 main 的網站視覺辨識、Google Safe Browsing／Web Risk 查核、手動截圖介面，保留既有獨立卡片和阻擋修正。遠端同時包含對話偵測 demo，保留為獨立 ChatRoom 功能，不自動讀取使用者聊天室。

## 預設與使用

`Settings.load()`、config 範例與本機設定預設開啟 LLM、內容上傳、網路查詢及 Safe Browsing。直接建立 `Settings()` 的離線程式／測試仍可使用保守設定。擴充功能首次套用此版本會保留配對碼並開啟後端、AI、自動截圖；之後可在設定自行關閉，不會每次啟動重新打開。

1. 在 `config/config.local.json` 填入 `api_key`（OpenAI）與 `google_url_reputation_api_key`（Google）；原 `google_safe_browsing_api_key` 也相容。Google key 可從 Google Cloud 建立專案、啟用 Safe Browsing API 後建立憑證。key 只放後端。
2. 啟動 `uv run python -m script.server`，在擴充功能填入 `var/extension-token.txt` 的配對碼。
3. 在 chrome://extensions 重新載入 extension，重新整理網頁。AI 與 Google 必须各自有有效 key；開關開啟不代表供應商已成功查詢。

## 程式分工

- `extension/src/background.js`：設定遷移、自動擷取目前作用中且聚焦視窗的可見 JPEG、每分頁／文件至少 60 秒節流、截圖前後核對分頁與導航。無痕不擷取；不保存截圖。手動按鈕可立即重查。
- `extension/src/core.js`：將後端新增的 VISION、GOOGLE_URL_REPUTATION 層合併至本機結果，避免丟失新層。沿用風險評分與獨立提醒卡片。
- `extension/src/options.js`、`options.html`、`src/coverage.js`：截圖獨立開關、資料用途说明、兩個新層的中文狀態。
- `script/vision.py`、`server.py`、`pipeline.py`：處理截圖、限制大小與格式、AI 視覺推論；沿用不執行頁面 JavaScript 的 L7。
- `script/google_reputation.py`：修正 V5 的 threatTypes 陣列解析；格式錯誤標示查詢失敗，快取限制 512 筆。
- `script/indicators.py`：舊 indicators 入口採正確 urls[] 參數，相容共用 Google key。
- `script/config.py`：載入預設與舊 key 相容。Google 查詢使用獨立設定，避免為其開啟網路時再次觸發整條管線 RDAP。
- `extension/tests/features.mjs`：真实 Chromium 截圖，自動上傳與預設遷移，使用模擬供應商回應驗證 Google／視覺評分與卡片；不冒充外部 API 實測。

規格依據：[Google V5 urls.search](https://developers.google.com/safe-browsing/reference/rest/v5/urls/search)、[Chrome captureVisibleTab](https://developer.chrome.com/docs/extensions/reference/api/tabs#method-captureVisibleTab)。自動截圖需 all_urls 權限；實際處理仍限定可分析的 HTTP(S) 網頁。

測試命令：`uv run python -m pytest -q`、`npm --prefix extension test`、`npm --prefix extension run test:features`、`npm --prefix extension run test:demo`。
