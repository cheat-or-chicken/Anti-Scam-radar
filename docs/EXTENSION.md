# Chrome 擴充功能整合與移植

## 本次完成

保留舊版的 NPA／TWNIC 名單、數字變體辨識、手動查網址、轉址追蹤、警示與繼續瀏覽流程。把資料匯入與查核邏輯移植至 Python，前端另保留低成本本機版本，讓離線時也能使用。

介面重做為奶白／墨綠的風險面板：目前網站、主動防護開關、具體訊號、每層涵蓋程度、手動網址查核、後端狀態、設定與全頁警示。所有可疑文字以 textContent 顯示，沒有將網頁輸入當作 HTML。基本內容偵測不依賴 popup 開啟。

## 功能對照

| 舊擴充功能 | 現在 |
|---|---|
| Windows 絕對路徑的 build_blocklist.js | `script.build_blocklist` 用 csv.DictReader 正確解析 CSV、合併 JSON、輸出來源 hash／統計期間，標準化 IDNA 與 PSL。舊檔只作命令轉接。 |
| 向上剝除所有子網域 | Python tldextract／JS tldts 均啟用 PSL PRIVATE，停止在可歸責邊界，避免共享平台連坐。 |
| 數字骨架 Set/Map | Python Blocklist.check 與 JS checkBlocklist；維持多樣本分組、排除純數字 label，只给低權重推測。 |
| 未命中就 safe | 改為「目前未發現警訊」，缺資料顯示 unknown／missing／error，明示檢查不完整。 |
| 隱藏分頁探路 | 移到 `POST /v1/check-url`，用既有 SafeFetcher 做受限 HTTP GET／轉址／靜態抽取；不自動執行可疑 JS、不共用使用者 cookies。 |
| service worker 全域 Map | session storage 保存每個分頁結果、documentId、jobId、轉址與臨時放行狀態。背景程序重新啟動不會清空所有判定。 |
| 只查網址 | DOM snapshot 主動加查政府機構冒用、可疑話術、站外表單、隱藏指令與新增敏感欄位。 |
| JS 跳轉追蹤 | 觀察使用者實際導覽的 webNavigation／webRequest；手動後端查核僅追 HTTP 跳轉，不宣稱完成動態探路。 |
| downloadItem.tabId 判斷探路下載 | 不再依賴 DownloadItem 沒有保證提供的 tabId。下載事件以實際下載網址比對名單後取消；页面點擊執行檔另有提前提醒。 |
| query string 帶原網址與警示資訊 | 警示頁只有隨機識別碼，內容由背景驗證 sender／tab 後從 session 讀取；原網址不放在警示頁 URL。 |
| popup 無差別發起高權限訊息 | 區分 content script / popup / options / warning；頁面不能要求設定變更、後端配對或放行網址。 |

## 新增／重構檔案

| 檔案 | 功能與技術 |
|---|---|
| `script/blocklist.py` | Blocklist.check、digit_skeleton、verify_blocklist；同一份名單供 CLI／後端使用。 |
| `script/build_blocklist.py` | 可重現的 CSV／JSON 匯入，移除不可辨識及 public suffix 目標，保留 hash 與日期，不把本次產檔時間當作最新通報時間。 |
| `script/data/blocklist.json` | 共用名單來源；32,627 個正規化網域、487 組數字變體，匯入快照而非線上查詢。 |
| `script/server.py` | FastAPI loopback API、Bearer 配對、Host／Origin 檢查、1 MB 上限、2 個並行／每分鐘 12 次限制、外部觀測欄位清除。 |
| `script/package_extension.py` | 白名單方式打 ZIP，只包含可載入的資產，排除 .git、node_modules、原始資料與 key。 |
| `script/pipeline.py` / `layers/adjudication.py` | 新增 BLOCKLIST 層；名單命中可單獨提高風險，信任清單仍依既有策略處理。 |
| `extension/manifest.json` | MV3、Chrome 120+、自動注入 top-frame content script、storage 權限、後端 connect-src 限定本機。 |
| `extension/src/core.js` | 可在 Node 測試的純本機分析：PSL、政府品牌、文案、表單、下載、裁決與不抹除本機證據的結果合併。 |
| `extension/src/background.js` | 名單載入、導航／轉址／下載事件、訊息授權、session 狀態、非同步結果防止套用至已切換的頁面、配對後端。 |
| `extension/src/content.js` | ISOLATED world 靜態採集，不取欄位值；MutationObserver 節流、敏感 focus／submit／下載 click 攔截、closed Shadow DOM 提示。 |
| `extension/src/api.js` | 固定 loopback 端點、omit credentials、拒絕 redirect、28 秒 timeout、明確錯誤狀態。 |
| `extension/popup.html` / `src/popup.js` | 主面板、風險摘要、tab 切換、訊號清單、涵蓋程度、手動 URL 檢查與防護開關。 |
| `extension/options.html` / `src/options.js` | 主動防護／本機後端／AI 許可、配對碼與實際連線測試，拒絕誤貼 sk- API key。 |
| `extension/warning.html` / `src/warning.js` | 高風險頁、理由、離開／5 分鐘相同 URL 放行；不能由網頁自選放行網址。 |
| `extension/icons/radar.svg` / `radar-*.png` / `render-icons.mjs` | 向量盾牌圖示與 Chrome 工具列用的多尺寸 PNG；Playwright 本機 rasterize，不載入外部圖片。 |
| `extension/ui.css` | 共用色彩／字體／間距、可鍵盤操作 focus 樣式、縮小畫面自適應、reduced-motion。 |
| `extension/build.mjs` / `package.json` / `package-lock.json` | esbuild bundle、固定 npm 依賴；複製 Python 的共用名單供 MV3 離線使用。 |
| `extension/background.js` / `content.js` / `popup.js` / `options.js` / `warning.js` | 可直接載入的產出檔，透過 npm run build 重建。 |
| `extension/blocklist.json` | 由 build 複製的共用快照，不應手動修改。 |
| `extension/THIRD_PARTY_NOTICES.txt` | 隨安裝包附上 tldts／tldts-core 的授權聲明。 |
| `extension/README.md` / `.gitignore` | 安裝、配對、來源與限制；排除 npm／測試截圖。 |
| `tests/test_extension_bridge.py` | Python 名單邊界、Bearer／Origin／大小限制、不能信任客戶端的 observed、無網路／無 LLM、速率上限。 |
| `extension/tests/core.test.js` | 本機風險判斷、PSL、OTP／正常內容對照、缺資料、不抹除證據。 |
| `extension/tests/browser.mjs` | 真正 Chromium 載入 MV3，驗證頁面偵測、DOM 更新、敏感操作、popup／manual、配對、Python 整合、警示頁與放行。 |

`extension/` 已作為一般目錄納入主專案，來源、測試與可載入的 bundle 都由主專案一起提交，沒有 submodule 或 gitlink。原獨立儲存庫的 Git metadata 已移至遷移工作區的 `var/git-backups/` 作為本機備份（不推送）；上游遠端儲存庫未變更。本版建置需使用主專案共用資料，已有 bundle 則能單獨安裝。`node_modules/`、測試產物、金鑰與 log 仍排除追蹤。

## 啟動與配對

先依 README 安裝依賴。在根目錄啟動 `uv run python -m script.server`，預設只綁定 127.0.0.1:8765。第一次以權限 600 建立 `var/extension-token.txt`；配對碼與 OpenAI API key 是不同憑證。OpenAI key 保持在 `config/config.local.json`，啟用 AI 需後端 `llm_enabled`、`allow_content_upload` 以及擴充功能自己的 AI 開關都允許。

Chrome 載入 extension 資料夾後即可基本防護；配對後才會上傳 snapshot 到本機。手動 HTTP 探路另受後端 `network_enabled` 控制；自動 snapshot 分析不做站外 GET。後端有資源限额時回 429，擴充功能保留本機結果。

API：`GET /health` 提供簡單可用狀態；`POST /v1/analyze` 接 `{context, include_llm}`；`POST /v1/check-url` 接 `{url, fetch_page, include_llm}`。POST 必须 Bearer token。Content script 只能提交 top frame 的當前頁面 snapshot，URL 以 Chrome 提供的 sender/frame 資料為準；不能製造可信動態外洩證據，後端也會清除 `network_trace`／`trace_collected`／`domain_age_days`／`tls_valid`。

## 已知限制

這是黑客松可執行整合，並非宣稱已達企業防毒或 Chrome Web Store 上架稽核標準。導航檢查在 commit 後介入，可能已有資源載入；手動檢查僅 HTTP，不追 JS／地區／Cookie 特定內容。DOM 採集不能跨網站 iframe、closed shadow root、canvas；網頁可能移除提示。提示使用者確認不能取代可信的 L4 網路觀測採集器。

系統 DNS 及執行緒的硬終止限制沿用 IMPLEMENTATION 文件。API 只供本機使用，不要直接改 host=0.0.0.0 對外公開；多使用者服務需要獨立認證、工作佇列、全域预算及 worker 隔離。

名單來源由原 clone 提供，未重新驗證通報時效或網站現況。瀏覽器與 Python 各自有本機规则，核心交界已測試，但不能假設所有未移植層在瀏覽器獨立運作。進階 L7、歷史、RDAP 等結果仍依實際資料與設定提供。

設計參考 Chrome 官方 [storage](https://developer.chrome.com/docs/extensions/reference/api/storage) 與 [content scripts](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts)。

## 本次驗證紀錄

Python 87 項測試與 Node 9 項核心測試通過；Chromium MV3 實際載入測試也通過，包括自動頁面／DOM 偵測、敏感欄位提示、手動網址查核、Bearer 配對、Python 回傳、警示頁及暫時放行。測試關閉真實 LLM／外部查證，目標站全部以 route fixture 替換。畫面檢查截圖在 extension/artifacts/（不提交）。
