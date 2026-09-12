# 品牌官方網址查證與語意分析 API

兩支 API 接受已爬取的網頁快照，不執行 JavaScript；品牌查證僅在需要確認 www 別名時，透過 SafeFetcher 檢查搜尋取得的官方入口轉址。由呼叫端傳入目前頁面最終 URL 與 `text`，或提供 `html` 讓 BeautifulSoup 抽取可見文字。只有 URL 無法完成語意判斷，回傳 `unknown`。標題與文字合計遮罩後最多上傳 12,000 字元；遮罩不是完整個資去識別，請勿送入登入後的私人內容。

## 啟用與呼叫

在 `config/config.local.json` 填入 `api_key`，並設定 `llm_enabled: true`、`allow_content_upload: true`；官方網址搜尋另需 `network_enabled: true`。環境變數 `OPENAI_API_KEY` 優先於設定檔。金鑰只在後端使用，不能填進 Chrome 擴充功能。擴充功能使用的是 `var/extension-token.txt` 配對碼。

啟動：`uv run python -m script.server`。修改設定後需重啟後端。這兩支端點的呼叫本身代表要求使用 LLM，沒有另外的 `include_llm` 欄位，但仍遵守後端三個開關。既有 `/v1/analyze` 與擴充功能仍保留各自的 LLM 選項，不會在每次自動偵測額外觸發付費官方搜尋。

```python
from pathlib import Path
import httpx

headers = {"Authorization": "Bearer " + Path("var/extension-token.txt").read_text().strip()}
payload = {"context": {
    "url": "https://711-payment.example/",
    "title": "台灣 7-ELEVEN 官方繳費服務",
    "text": "我們是台灣 7-ELEVEN 官方繳費服務，請將 OTP 交給客服。"
}}
# 品牌查證包含 3 次模型請求；呼叫端 timeout 應大於 3 * (timeout_seconds + 1)。
with httpx.Client(timeout=250) as client:
    brand = client.post("http://127.0.0.1:8765/v1/verify-brand", headers=headers, json=payload)
    semantics = client.post("http://127.0.0.1:8765/v1/analyze-semantics", headers=headers, json=payload)
    print(brand.json())
    print(semantics.json())
```

## `POST /v1/verify-brand`

1. LLM 從內容辨認「自稱品牌」與地區，引用原文佐證。新聞提及、販售他牌商品不應被當成自稱官方。
2. 使用 OpenAI Responses API `web_search` 真正搜尋。搜尋只接收抽取出的品牌與地區，不傳目標 URL 路徑或整份頁面。強制搜尋，最多兩次工具呼叫，受 `max_tool_calls` 限制。
3. LLM 根據搜尋研究選出官方来源索引。程式要求索引落在 API 真正回傳的 `web_search_call.action.sources` 中；文字憑空生成的 URL 不會被採納。
4. 程式比對 HTTPS 與 IDNA 正規化後的完整主機名稱，不採字串包含比對，也不把任意子網域或共用主機租戶當官方。只有 www 差異時，由具 SSRF 防護的 SafeFetcher 驗證搜尋支持的官方根入口是否轉向待查主機；無法確認則 match 為 unknown。最多多一次 HTTP 抓取，請求總等待上限應再加 timeout_seconds + 1。

成功回傳 `status: ok`、`claimed_brand`、`claim_quote`、`official_urls`（可供 UI 顯示可點擊來源）、`checked_host`、`match: match|mismatch|unknown`、`confidence` 與說明。查證仍為 `evidence_grade: inferred`：有來源不等於來源本身可信；模型可能誤選來源、搜尋可能未收錄合法服務。`mismatch` 表示未符合本次查得入口，不直接等於詐騙；`match` 也不是安全保證。不自動加入白名單或觸發硬封鎖。

## `POST /v1/analyze-semantics`

單次結構化 LLM 呼叫，分析轉交密碼/OTP、緊急付款、保證獲利、遠端控制、冒用身分及提示詞注入。要求區分正常登入／付款、新聞與防詐引用。回傳 `verdict: suspicious|clean|unknown`、`confidence`、`findings`（類別、逐字摘錄、固定中文說明）。程式核對摘錄確實存在於送出的文字；矛盾或捏造證據回傳 `unknown`，低信心不給確定結論。

## 失敗、費用與限制

未啟用、無內容、缺乏明確自稱、搜尋無來源、來源歧義、逾時、拒答、API 錯誤、呼叫額度不足均保守回傳 `status: unknown` 與原因代碼，不當成安全。維持配對驗證、每分鐘 12 次、同時 2 次請求及 1 MB 請求上限；HTTP 401/403/413/422/429 分別表示驗證、來源、大小、格式與流量限制。各請求不持久保存頁面或金鑰，Responses 使用 `store=False`；此參數不代表供應商完全不保留濫用監控資料。

品牌查證最多 3 次模型請求，語意分析 1 次，受 `max_llm_calls` 限制。搜尋另有工具費用。預設每次模型請求 12 秒可能不足以完成搜尋，可把 `timeout_seconds` 調整至 60；不可超過設定驗證上限。本次測試保留原模型，將本機 timeout_seconds 設為 60、max_output_tokens 設為 3000，以容納搜尋與結構化回應。

## 檔案與技術

| 檔案 | 功能與技術 |
| --- | --- |
| `script/site_checks.py` | `verify_brand`、`analyze_semantics` 獨立 async function；Pydantic 嚴格 JSON Schema、Responses 搜尋來源驗證、原文摘錄驗證、IDNA 主機比較、保守失敗處理。可注入既有 `LLM` 以重用額度和進行離線測試。 |
| `script/server.py` | FastAPI 兩支 POST 路由；重用配對驗證、負載／速率限制，完成後關閉 LLM client。 |
| `tests/test_site_checks.py` | 模擬 API 回應測試品牌比對、偽造來源、歧義、摘錄、HTML、錯誤、開關、預算與 HTTP 驗證。 |
| `config/config.local.json` | 本機金鑰與開關；已忽略 Git，不應提交。 |
| `docs/LLM_APIS.md` | 本文件，介面、呼叫範例、設定與限制。 |

OpenAI 官方介面依據：[Web search](https://developers.openai.com/api/docs/guides/tools-web-search)。

## 測試重跑

離線回歸：`uv run pytest -q`（114 項）及 `uv run ruff check script tests`。擴充功能：`npm --prefix extension test`（9 項）及 `npm --prefix extension run test:browser`（真實 Chromium）。

`script/smoke_site_checks.py` 是可重跑的真實 API 測試入口，執行 `uv run python -m script.smoke_site_checks`。它透過 FastAPI ASGI HTTP 路由使用本機設定和真實 OpenAI API，會付費，包含官方／仿冒 7-ELEVEN、冒用監理站索取 OTP、防詐宣導、正常 OTP 登入、新聞提及品牌六個案例，並檢查回傳結果；失敗以非零 exit code 結束。此測試使用合成文案，沒有把真實私人瀏覽內容送出。LLM 與搜尋結果具有變動性，測試通過不代表已驗證所有詐騙場景或達成特定準確率。

### 本次驗證紀錄（2026-09-12）

- Python：114 passed；Ruff：通過。
- Extension：9 passed；Chromium：主動偵測、popup、欄位變更警示、配對後端串接、黑名單攔截／略過均通過。
- 真實 OpenAI：已觀察到官方 7-ELEVEN → match、仿冒入口 → mismatch、索取 OTP → suspicious、防詐宣導與正常 OTP → clean、新聞提及 → no_clear_brand_claim。
- 六案例 HTTP smoke 的該次結果為四項符合预期、兩項品牌查證回 official_site_uncertain（unknown），因此程式 exit 1，沒有宣稱全部即時案例穩定通過。原始結果在本機 `var/site-checks-live.jsonl`（忽略 Git）。再單獨診斷官方入口時回 match；顯示搜尋／LLM 具有波動。未降低信心門檻、未把 unknown 改成安全、未用硬編碼 7-ELEVEN 網域取代真實搜尋。
- 測試揭露 www 別名問題，已加入受 SSRF 防護的官方轉址確認，以及兩項離線回歸案例。爬取仍僅 HTTP，不執行 JS。
