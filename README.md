# Anti-Scam Radar

## 對話防詐 Demo v1

目前對話功能位於 `ChatRoom/`，包含14個可重播案例（6詐騙、8正常）、逐則示警、原文證據與後續預測。

```bash
uv sync --locked --python 3.12 --extra dev
cp .env.example .env.local
# 編輯 .env.local 填入自己的 OPENAI_API_KEY，不要提交此檔
PORT=8010 uv run python ChatRoom/server.py
```

開啟 http://localhost:8010/，選案例後按「載入」。PowerShell 可先執行 `$env:PORT="8010"` 再執行啟動命令。

- [聊天室操作與設定](ChatRoom/README.md)
- [14案例索引](docs/擴充對話案例索引.md)
- [三次重播測試](docs/擴充案例三次測試報告.md)
- [整篇預測重評](docs/完整對話預測命中重評.md)

42次重播共690則分析完成；預測整篇複核為24命中、19未命中、8不明確，可判定部分55.8%。這是合成開發資料結果，不代表真實世界準確率。整篇評分目前僅離線使用，網頁仍保留先前逐輪核對；UI優化留待下一階段。


台灣防詐驗證腳本。提供 L0–L17 的 function 入口、CLI、政府機關冒用偵測、受控行為證據判讀、L7 LLM 靜態程式碼審查、查證工具、SQLite 稽核與合成評估集。目前已整合 Chrome 擴充功能，提供主動頁面偵測、美化風險面板與可選用的本機 HTTP 後端。


## Chrome 擴充功能

擴充功能已整合至本專案的 `extension/`，clone 本專案即可取得後端與擴充功能，不需要另外 clone 或初始化 submodule。

直接在 Chrome 的 `chrome://extensions` 開啟開發人員模式，載入專案的 `extension` 資料夾，再重新整理欲檢查的頁面。基本防護不需後端與 API key。

進階分析先執行：

```bash
uv sync --locked --python 3.12 --extra dev
uv run python -m script.server
```

擴充功能設定中貼入 `var/extension-token.txt` 的**配對碼**並測試連線。OpenAI key 仍留在 `config/config.local.json`。詳見 [擴充功能使用說明](extension/README.md) 與 [移植／整合文件](docs/EXTENSION.md)。

可攜安裝包由 `uv run python -m script.package_extension` 產生於 `var/anti-scam-radar-extension.zip`，解壓縮即可載入，不含 key 與原始資料集。

## 執行

需要 Python 3.12+ 與 uv，在專案根目錄執行：

```bash
uv sync --locked --python 3.12 --extra dev
uv run scam-radar analyze fixtures/government-phishing.json
uv run scam-radar analyze fixtures/official-login.json
uv run scam-radar layer fixtures/observed-exfiltration.json L4
uv run scam-radar tool fixtures/government-phishing.json psl_resolve
uv run pytest -q
uv run python -m script.evaluate
```

預設不連網、不使用 LLM，也不需要 API key。所有輸出均為 JSON；`unknown` 是資料不足，`clean` 只表示沒有命中已執行的規則。`decision.coverage` 固定為 `partial`，不宣稱已完整檢查網站。

## API key

本次工作區已建立 `config/config.local.json`，直接填入 `api_key`。新 clone 請先執行：

```bash
cp config/config.example.json config/config.local.json
chmod 600 config/config.local.json
```

啟用 LLM 時，將 `llm_enabled` 與 `allow_content_upload` 設為 `true`。後者表示允許將截斷、初步去識別化後的頁面／JS 片段送到 OpenAI；遮罩不是完整的個資清除器，不應輸入真實密碼、表單值或私密頁面。`OPENAI_API_KEY` 環境變數優先於設定檔。不要把 key 放到前端。

啟用 RDAP、憑證查詢與主動 GET 時，另設 `network_enabled: true`。此開關只控制查證網路；LLM API 由 `llm_enabled` 控制。啟用 function calling 調查：

```bash
uv run scam-radar analyze fixtures/government-phishing.json --deep
```

示範網址使用保留的 `.example`，不能拿來驗證真實連線；網路工具可自行呼叫 `PageContext(url="https://example.com")` 等公開測試站。

模型、逾時、LLM／工具呼叫上限及資料庫位置都可設定。預設模型為 `gpt-5.4-mini`，`code_model` 可另外設定；模型存取權依帳號而定。本次沒有 key，未執行真實付費 API 測試。

## 程式入口

```python
import asyncio
from script.config import Settings
from script.models import PageContext
from script.pipeline import analyze
from script.layers.rules import verify_l2

ctx = PageContext(
    url="https://mvdis.gov.tw.fake.example/notice",
    title="監理服務網",
    domain_age_days=3,
    sensitive_fields=["credit_card"],
    behavior="sensitive_field_focus",
)
print(verify_l2(ctx).model_dump())
print(asyncio.run(analyze(ctx, Settings.load())).model_dump())
```

本機 HTML 可先轉換成 snapshot：

```bash
uv run scam-radar extract page.html --url https://demo.example/ > snapshot.json
uv run scam-radar analyze snapshot.json
```

CLI 全域的 `--config` 必須放在子命令前面。完整逐檔說明、每層實作範圍、工具入口及架設邊界，見 [實作文件](docs/IMPLEMENTATION.md)。

## L7 程式碼合理性審查

把 JavaScript 原始碼放在 PageContext 的 `scripts` 陣列，使用 `uv run scam-radar layer snapshot.json L7` 或 `uv run scam-radar tool snapshot.json code_review`。L7 回传 `feedback`，包含片段索引與需核對的程式行為；不執行 JavaScript，不產生 observed 外洩證據。缺 key／程式碼時回 unknown，缺上傳許可時回 skipped。原 `sandbox_replay` 工具保留為相容別名，現在也只做靜態審查。

申請 key：登入 [OpenAI Platform API keys](https://platform.openai.com/api-keys)，在專案建立 secret key；API 用量與付款在 [Billing](https://platform.openai.com/settings/organization/billing/overview) 管理。流程參照 [官方 Quickstart](https://developers.openai.com/api/docs/quickstart)。取得後只修改本機設定檔的以下欄位，保留其他設定：

```json
{
  "api_key": "你的 API key",
  "llm_enabled": true,
  "allow_content_upload": true
}
```

只做 LLM 程式碼審查時，`network_enabled` 可以保持 false。

新增的品牌官方網址搜尋與網站語意分析 API，請見 [LLM API 使用文件](docs/LLM_APIS.md)。

品牌近似網域、資料不足提示與查證指標 API，請見 [指標補強文件](docs/DOMAIN_INDICATORS.md)。

各層資料取得、重掃保留及等待狀態，請見 [層級覆蓋修正](docs/LAYER_COVERAGE.md)。

五個可互動、經真實擴充功能驗證的本機展示頁：[RADAR LAB 操作與講稿](demo/README.md)。啟動 `uv run python -m script.demo_server` 後在 Chrome 開啟 `http://127.0.0.1:8088/`。

警示漏顯示修正、白話說明與多語言話術分類：[警示與語意補強](docs/WARNINGS_AND_SEMANTICS.md)。
