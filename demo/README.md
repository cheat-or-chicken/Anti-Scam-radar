# RADAR LAB：五個互動展示情境

啟動後在 **Google Chrome** 開啟 [展示總覽](http://127.0.0.1:8088/)。不要用 file:// 直接開 HTML，也不要在沒有安裝擴充功能的內嵌預覽瀏覽器期待看到警示。

```bash
# 專案根目錄
uv run python -m script.demo_server
```

此服務獨立於 8765 的分析後端，只監聽 127.0.0.1:8088。macOS 本機 80 埠需要額外權限，因此 URL 驗證器僅新增 `http://127.0.0.1:8088` 的固定例外；任意外部 8088 埠仍拒絕，SafeFetcher 的私有 IP／SSRF 阻擋也保持有效。這只允許分析瀏覽器提供的本機快照，沒有放寬主動爬取本機服務的權限。

## 展示前準備

1. Chrome 開啟 `chrome://extensions`，重新載入專案的 `extension/`（已重新 build）。如尚未安裝，開啟開發人員模式 → 載入未封裝項目 → 選該資料夾。
2. 保留「主動防護」開啟，**暫時關閉擴充功能的本機後端加查**。這份示範測試的是本機主動防護；不依賴 API key、LLM 或外部威脅名單。展示完成可再打開後端。沒有自動更改你的擴充功能設定。
3. 從總覽依序進入情境，每頁等候 1～2 秒。可點工具列圖示查看具體命中層，或直接觀察右下角提醒。
4. 若先前曾選擇繼續瀏覽，關閉該分頁再從總覽開新分頁，避免五分鐘臨時放行影響示範。

## 建議講稿（約 3 分鐘）

| 情境 | 操作 | 已實測的本機結果 | 可以說明什麼 |
| --- | --- | --- | --- |
| 01 假交通罰單 | 開啟，然後點付款欄位 | L2 品牌網域不符 + L3 催繳，60 分 banner | 即使頁面像官方，主機仍不是官方；敏感操作前再確認。 |
| 02 高報酬投資 | 看虛構績效圖，再點會員密碼 | L3 保證收益話術，40 分 banner | 漂亮圖表不會抵銷可疑承諾。 |
| 03 假客服遠端協助 | 看客服訊息，點模擬協助 | L3 遠端控制軟體要求，45 分 banner | 辨識要求安裝遠端工具的文字；本頁沒有安裝檔。 |
| 04 索取簡訊驗證碼 | 點 OTP 欄位 | L3 轉交 OTP，55 分 banner；操作前確認框 | 區分自己登入與把驗證碼交給他人。 |
| 05 延遲領獎表單 | 等首次檢查完成，再點「開啟領取流程」，等約 5 秒 | 初始 0 分；加入 OTP 話術、欄位後，L3 + L8 + L15 共同觸發 block | 初次掃描無警訊不代表後續安全；MutationObserver 持續檢查。 |

總覽頁是陰性對照，實測 0 分。側欄僅為操作說明；警示、敏感操作確認與封鎖頁都由真正的擴充功能產生，不是網站繪製的假警示。分數是這組合成內容的規則結果，不是未知網站的詐騙機率。

所有頁面清楚標示教學模擬。表單 submit 會取消，CSP 禁止 form-action 與 connect，HTTP POST 回 405；沒有讀取輸入值、真實付款、外部資源、資料儲存或程式下載。請只用 placeholder 指定的虛構資料。

## 檔案與技術

- `index.html`：展示入口、五個情境卡片、操作準備。
- `traffic.html`、`investment.html`、`support.html`、`otp.html`、`prize.html`：獨立靜態情境頁，各有模擬服務介面、操作說明與下一頁導覽。
- `demo.css`：共用 CSS Grid、色彩主題、純 CSS 雷達圖、響應式版面及鍵盤焦點樣式，沒有 CDN、字型或圖片依賴。
- `demo.js`：阻止提交、模擬按鈕，以及領獎頁透過 DOM API 動態插入表單；不讀取 input value，不發網路請求。
- `script/demo_server.py`：Python 標準庫 HTTP 服務、固定靜態檔白名單、CSP、防目錄穿越、禁止 POST、關閉含網址的 access log。
- `script/domains.py`、`extension/src/core.js`：固定 loopback demo 埠支援，無網址白名單加分、無情境專用偵測後門。
- `extension/tests/demo.mjs`：Playwright 實際載入 MV3，以真實本機 HTML 驗證五情境、總覽對照、OTP 操作、動態攔截、無資料外送及手機版。
- `tests/test_demo.py`：HTTP 檔案白名單、CSP／POST 限制、URL 埠邊界與 SSRF 保持阻擋。

## 重跑

先保持 demo server 執行，再執行：

```bash
npm --prefix extension run build
npm --prefix extension run test:demo
uv run pytest -q
```

測試使用獨立 Chrome profile，不變更你的瀏覽器設定，也不會關閉 8765 的現有後端。輸出報告與真實畫面截圖在 `extension/artifacts/demo/`（不提交 Git）。
