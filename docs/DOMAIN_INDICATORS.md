# 網域與查證指標補強

本次針對使用者提供的 `ftec-08.twietio.vip` 案例補強通用規則，沒有把單一網址硬編碼成黑名單。使用的 URL 是 `https://ftec-08.twietio.vip/`；貼文末尾的反斜線不是網址內容，API 仍會拒絕反斜線。

## 證據與行為

2026-09-12 本機 SafeFetcher 對該入口的 HTTP GET 得到 404，因此不能確認網站目前的品牌文案、付款欄位或惡意程式。使用者貼出的 IP、日期、排名、Google 查詢及註冊商評語是外部報告，不直接當成本次工具已驗證的事實。

`ftec` 是 `fetc` 相鄰字母對調，`ftec-08` 又帶編號，且不位於維護的 `fetc.net.tw` 官方網域。本機 Python L1 與 Chrome 都新增這項規則：完整 label 中的維護品牌 token 或相鄰轉置，帶數字序號給 35 分、不带序號給 25 分；同品牌只計一次。官方域名與其子域、任意連字號／數字、任意 `.vip`、名稱中的子字串都不因此命中。不採一般短字串模糊距離，避免泛化成大量誤報。

此案例僅有網址證據時顯示 banner，提示自行前往官方入口查詢、不要在此提供付款資料或 OTP；不宣称人工確認詐騙，不單憑此硬封鎖。若另有冒用標題、催繳或敏感資料外傳，既有分層裁決會繼續累積獨立訊號。

官方資料：[遠通電收防繳費詐騙公告](https://www.fetc.net.tw/ContentFiles_UX/Announcement/856/index.html)。維護名單僅收錄已核對的 `fetc.net.tw`，不宣稱列全所有授權服務商。

## 新 API

`POST /v1/indicators`，沿用本機後端 Bearer 配對、Host／Origin、請求大小、速率與並行限制。例：

```python
from pathlib import Path
import httpx

with httpx.Client(timeout=190) as client:
    response = client.post(
        "http://127.0.0.1:8765/v1/indicators",
        headers={"Authorization": "Bearer " + Path("var/extension-token.txt").read_text().strip()},
        json={"context": {"url": "https://ftec-08.twietio.vip/"},
              "fetch_page": True, "checks": ["registration", "safe_browsing"]},
    )
    print(response.json())
```

`context` 也能傳入 `text`／`html`；預設不重新抓網頁、不執行外部查詢。`fetch_page` 需要 `network_enabled`。重新抓取失敗會清掉用於內容判斷的客戶端文字，不能拿舊快照宣稱這次抓取成功。所有抓取沿用 SSRF 防護、DNS/IP 檢查、TLS 驗證、每跳轉址重驗、位元組及時間上限，不執行 JavaScript。

`checks` 只允許 `registration` 和 `safe_browsing`，各最多一次，受 `max_tool_calls` 限制。輸出逐項區分 `observed`（取得資料）、`suspicious`（推測訊號）、`matched`（供應商名單命中）、`not_listed`（實際查詢未列入）、`not_matched`（本機規則未命中）、`unknown`（未取得／未啟用）。報告不把缺資料累積為分數，也不以名單未命中抵銷其他警訊。

## Google Safe Browsing

新增兩個設定：

```json
{
  "safe_browsing_enabled": false,
  "google_safe_browsing_api_key": ""
}
```

需自行在 Google Cloud 專案啟用 Safe Browsing API 並建立對應 key，再填入 `config/config.local.json`；OpenAI key 無法替代。`network_enabled` 與 `safe_browsing_enabled` 都必須開啟。此項會將完整待查網址送給 Google，預設關閉，沒有偷偷共用內容上傳許可。未填 key、HTTP 錯誤、API 拒絕、無效回應或未知威脅類型都回 unknown。未開啟時不顯示「查詢未命中」。

使用 [Google v5 urls.search](https://developers.google.com/safe-browsing/reference/rest/v5/urls/search) 的固定端點，已加入離線契約測試；本次没有 Google key，因此未宣稱真實 Google 查詢測試通過。這份指標 API 僅呈現結果，尚未自動將 Google 結果接入擴充功能裁決／封鎖。商用需另外評估 Google Web Risk，詳見 [官方 API 說明](https://developers.google.com/safe-browsing/reference/rest)。

## 與提供指標的對應

| 指標 | 本次處理 |
| --- | --- |
| 品牌近似、序號子域、官方網域、交通催繳 | Python + Chrome 主動規則；避免把任意 hyphen 或 TLD 判成詐騙。 |
| 空白、404、挑戰頁、未取到表單／連結 | 標示覆蓋不足；Chrome 無可讀內容時不將文案／表單層標成已檢查，popup 顯示不足提示。 |
| Google 官方安全庫 | 新增可選 v5 真正查詢；沒有 key 明確 unknown。 |
| 註冊日期、年齡、週期 | API 從 RDAP 實際取得註冊與到期事件，保留 UTC 日期與查詢時間；不沿用使用者貼文日期。 |
| HTTP 安全標頭 | 抓取時擷取 CSP、HSTS、nosniff、Referrer-Policy 的存在狀態；不把缺少當成詐騙證明。 |
| SEO、購物結構、聯絡資訊 | HTML metadata／連結數、購物／聯絡用語觀察，不能當正規商家認證；robots/sitemap 尚未抓取。 |
| 詐騙站群分析 ID | 擷取 GA／GTM ID 供後續調查；沒有站群關聯資料庫，不宣稱共用 ID 等於同一犯罪集團。 |
| 通報與人工清單 | 沿用 NPA／TWNIC 匯入名單及既有人工指紋機制；沒有新增「人工確認網域」名單或把此案例加入。 |
| 語意與 L7 | 提示詞補上 404、CDN、無 MX、低流量等不能當成安全或定罪依據；L7 仍純靜態，不執行 JS。 |
| Tranco、MX、公司法人／實體一致性、IP 國家、憑證日期 | 新 API 明確標為尚未接入資料來源；不製造「無 MX」「註冊商常被濫用」等結論。既有 crt.sh 工具仍可另行查詢，非此次即時憑證驗證。 |
| Cloudflare／ASN、隱私保護、註冊商、一年期 | 不單獨加風險分；CDN 節點國家不等於商家實際所在地。 |
| LINE、投票、求職、模板商城等特殊場景 | 既有語意 API 可分析提供的文案，尚未新增各場景專用資料來源／驗證器。 |

## 檔案

- `script/brand_patterns.py`：可單獨呼叫的品牌 token 與相鄰轉置判斷。
- `script/data/brands.json`：新增遠通官方域名、品牌 token、引用來源，Python／JS 共用。
- `script/indicators.py`：`inspect_content`、`safe_browsing`、`registration`、`inspect_indicators` 函式入口與資料完整性報告。
- `script/server.py`：受驗證保護的 `/v1/indicators` 路由。
- `script/config.py`／`config/config.example.json`：Google 獨立 key 與許可設定。
- `script/network.py`：僅回傳選定安全標頭，避免回傳 Set-Cookie 等敏感資訊。
- `script/layers/rules.py`、`adjudication.py`：L1 整合，L3 錯誤頁未知，分類文案改為品牌／機構而非全部稱政府。
- `script/llm.py`、`site_checks.py`：補充內容不足與弱基礎設施指標的提示詞約束。
- `extension/src/core.js`、`src/popup.js`：同步主動偵測、覆蓋判斷及無資料提示；根目錄 bundle 已重新建置。
- `tests/test_indicators.py`、`extension/tests/core.test.js`、`tests/browser.mjs`：網址邊界、誤報對照、外部 API／失敗契約，以及真實 Chromium 載入模擬 404 頁的警示測試。

## 本次驗證

139 項 Python 測試、11 項 Node 測試、Ruff 及真實 Chromium 整合測試通過。瀏覽器以攔截回應的 404 fixture 測試該網址，確認 banner 而非 block，沒有在測試瀏覽器執行真實可疑站的 JavaScript。

實際 HTTP 抓取不可用；RDAP 取得 `twietio.vip` 註冊日 `2025-12-30T10:45:35Z`、到期日 `2026-12-30T10:45:35Z`，本次查詢時年齡 255 天、週期 365 天。Google 未啟用，回 unknown。原始本機報告：`var/domain-indicators-live.json`，不提交 Git。

重新啟動 Python 後端，Chrome 的擴充功能管理頁按「重新載入」，再刷新測試頁即可使用新本機警示。`var/anti-scam-radar-extension.zip` 也已重新打包。獨立指標 API 仍需以 POST 呼叫，未把所有遠端指標做成 popup 新面板。
