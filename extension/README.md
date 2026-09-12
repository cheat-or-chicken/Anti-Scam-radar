# 防詐雷達 v2

以既有 Chrome MV3 擴充功能重構，整合 Anti-Scam-radar 的 Python 驗證核心。

## 安裝

1. 在 Chrome 開啟 `chrome://extensions`。
2. 開啟「開發人員模式」→「載入未封裝項目」。
3. 選取這個 `extension` 資料夾（或 ZIP 解壓縮後的資料夾）。
4. 將防詐雷達釘選到工具列。既有分頁重新整理一次，啟用頁面內容偵測。

不需後端也能主動比對通報名單、網域變體、政府冒用、可疑文案與表單。資料不足不顯示「安全」。Chrome 內部頁、Chrome Web Store 等保留頁不開放內容注入。

## 使用

- 瀏覽頁面時自動檢查，不必開啟 popup。SPA 網址變更與新增敏感欄位也會重查。
- 點工具列圖示查看風險原因、資料涵蓋程度與每層回饋。
- 中等風險顯示可關閉橫幅；進入敏感欄位或送出表單前，再確認一次。
- 通報名單／高風險頁面會導向擴充功能警示頁；選擇繼續僅對當前分頁的相同完整 URL 放行 5 分鐘。
- 貼上其他網址查核，不會在使用者瀏覽器開啟隱藏分頁。

名單為隨程式附帶的匯入快照，**不是即時更新**；命中只表示資料庫列有這個網域，仍可能過期或誤報。一般瀏覽保護基於導航事件，在頁面 commit 後介入，不保證可疑資源從未載入。這個版本沒有宣稱具備網路層預先阻斷功能。

## 進階分析

在上層 Anti-Scam-radar 專案執行：

```bash
uv sync --locked --python 3.12 --extra dev
uv run python -m script.server
```

到擴充功能設定中，開啟本機後端，將專案 `var/extension-token.txt` 的配對碼貼入並測試。服務固定在 `http://127.0.0.1:8765`。**不要把 OpenAI API key 貼進擴充功能**，它仍放在後端 `config/config.local.json`。

AI 功能需同時開啟擴充功能的 AI 許可與後端 `llm_enabled`／`allow_content_upload`，並填入可用 key。L7 僅做靜態程式碼合理性審查，不執行任何 JS。需要 HTTP 轉址探路時，後端還需 `network_enabled: true`；只會使用受限 GET，不會進行瀏覽器 JS 跳轉。

後端不可用时，本機防護仍持續運作。API／網路查核可能失敗，不會因此把網站判為安全。

## 隱私與資料

基本偵測資料留在擴充功能內。開啟後端才會把標題、頁面文字、欄位種類與 inline script 送到本機；開啟 AI 後，相關片段才可能經後端送到 OpenAI。沒有讀取 input value、Cookie 或網路請求本文，也不將它們保存在紀錄。靜態文字仍可能包含個資，請不要在私密頁面開啟進階分析。

為支援警示後返回，完整目前 URL 暫存 `chrome.storage.session`，不寫入永久瀏覽紀錄；關閉分頁會清除，重啟瀏覽器亦會清空。OpenAI key 不在擴充功能中；後端配對碼只存本機、不使用 Chrome Sync、content script 不能讀取。

來源 `DEVLOG.md` 是舊版歷史紀錄，其中隱藏分頁、10 秒沙箱、27 項測試描述不代表 v2 的現況。NPA CSV／TWNIC JSON 保留為資料輸入；資料匯入器已搬到 Python。

## 開發

這份 extension 已改由 Anti-Scam-radar 主專案直接追蹤，與 `../script` 共用名單與品牌資料。請在主專案統一執行 Git 提交與推送，不需要另外設定 extension 的遠端或初始化 submodule。

```bash
# 在上層專案
uv run python -m script.build_blocklist
npm --prefix extension ci
npm --prefix extension run build
npm --prefix extension test
npm --prefix extension run test:browser
uv run python -m script.package_extension
```

浏览器測試首次需 `node extension/node_modules/playwright/cli.js install chromium`。測試後端停用 LLM 與外部網路，目標網站全部由 Playwright route 提供合成回應。`src/` 是維護來源，根目錄 `.js` 是 esbuild bundle；不要直接修改 bundle。安裝使用已打包檔案，不需要 Node。
