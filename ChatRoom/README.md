# 本機聊天室 API

在此資料夾執行：

```powershell
python server.py
```

開啟 `http://localhost:8000` 後，聊天室每一則自己或對方的訊息都會保存到 `chat_history.json`。

## API

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| `GET` | `/api/chat` | 取得完整聊天室內容，回傳 `{ "messages": [...], "count": 3 }`。可加上 `?counterpart=小明` 只取與小明的對話。 |
| `POST` | `/api/messages` | 新增訊息；JSON 為 `{ "text": "你好", "sender": "mine", "counterpart": "小明" }`，`sender` 可為 `mine` 或 `theirs`。 |
| `DELETE` | `/api/chat` | 清空所有已保存的聊天室內容。 |

例如取得完整紀錄：

```powershell
Invoke-RestMethod http://localhost:8000/api/chat
```

在網頁選取 `小明.txt` 時，檔名會成為目前對象「小明」。之後存入的每筆訊息都包含 `counterpart: "小明"`，因此切換其他 `.txt` 對象後，紀錄仍可明確區分。

## 防詐對話整合

從儲存庫根目錄執行 `python3 ChatRoom/server.py`，預設連至 `http://localhost:8000`。
依賴沿用專案的 `openai` 與 `pydantic`。伺服器端需設定 `OPENAI_API_KEY`；
`DIALOGUE_MODEL` 可指定模型，預設沿用網站偵測專案的 `gpt-5.4-mini`。
可用 `PORT=8001 python3 ChatRoom/server.py` 避開已使用的連接埠。

- 內建14例，或匯入 `*.replay.json`，以 `sender`、`channel` 呈現角色與分隔線。
- TXT 模式仍可輸入自己的回覆，雙方訊息共同累計輪次。
- 下一則／自動重播會先等待本輪API完成。暫停不取消已送出的API請求。
- 右側呈現示警、原文引用、七幕標籤、先前預測的核對與首次示警輪次。
- 案例名稱只供顯示，後端只讀allowlist訊息欄位，不讀檔名、標註或未來訊息。
- 對話目前以完整已見前綴加上一輪判斷維持脈絡，最多300則；尚未做長對話摘要壓縮。
- 逐輪log存在 `var/dialogue/`（不提交Git），畫面亦可匯出分析JSON。
- API或引用驗證失敗顯示analysis_error，不能當作正常或沒有誤報。
- 網址調查已串接：訊息與附件說明中的 URL 會自動讀取公開 HTML，結果獨立於對話分析顯示。示例或失效網域可能無法取得內容，不代表安全。

執行三例真實模型測試：

```bash
python3 -m ChatRoom.evaluate_dialogue --output var/dialogue-live
```

報表與每輪結果在指定目錄。三例為開發驗收資料，通過不代表真實世界準確率。
測試使用相同Detector，僅評測端讀取annotations的付款輪次與正常／詐騙標籤。

API：`POST /api/sessions`建立工作階段；`POST /api/analyze`接收
`{"session_id":"...","message":{"turn":1,"sender":"user","channel":"chat","text":"你好"}}`。
相同輪次及內容重送回原結果，不重複呼叫；改變已分析內容需新工作階段。
使用伺服器記憶體保存工作階段，重啟需重新開始。只監聽本機，不是多人正式部署服務。

結構化輸出參考：[OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)。

可在儲存庫根目錄建立 `.env.local`，寫入 `OPENAI_API_KEY=你的key`。非空值優先於繼承的環境變數；檔案已加入Git忽略。修改後重啟伺服器，以建立使用新憑證的API client。支援DIALOGUE_MODEL；其餘變數不從檔案載入。

### 引用與失敗重試（dialogue-v4）

模型只輸出evidence_turns，程式從已播放原文擷取引用，不要求LLM逐字重抄。輪次越界仍拒絕。最新失敗輪次可按「重試本輪分析」，重試成功覆寫該輪結果，不增加輪數；成功輪次重送仍回快取。分析失敗時暫停後續重播。錯誤訊息區分API額度、憑證與模型驗證問題。


### Demo v1 交接

使用14案例清單：`data/evaluation_suites/expanded-v1.json`。其中偵測器雜湊鎖定當時測試版本，後續程式修改後不可把同一清單冒充全新同版本測試；要重跑請另建版本清單。

`python -m ChatRoom.rescore_conversation_predictions` 只對既有 `reports/expanded-v1` 的預測做整篇離線語意重評，不重新分析風險。原始自動評分及助理逐筆複核分開保存於 `reports/prediction-whole-conversation-v2/`，後者不是獨立人工真值。

舊版交付ZIP已移除。共用領域知識保留在 `knowledge/detector/sources/`，B堆摘要在 `data/evaluation_suites/expanded-v1-sources/`，可重播資料在 `data/reconstructed/`。歷次評測報告為判斷變更的依據，保留供夥伴追溯。


## 訊息網址即時查核

從根目錄執行 `uv run python -m ChatRoom.server`，開啟 http://localhost:8000，選 `LINK_DEMO.replay.json` 後逐則播放。也可上傳 TXT／JSON，TXT 模式可手動輸入。沿用 config/config.local.json 的 LLM 與網路設定；不需把配對碼或 API key 放在聊天室前端。

訊息送出分析時立即擷取 http(s)、www、裸網域與附件 caption 內的網址。每個 URL 獨立卡片，兩個並行、同場重播去重；重設後不接受舊工作階段結果。只分析已播放訊息，不預讀未來網址。對话 API 暫時失敗也不會撤銷已完成的網址查核。

`POST /api/check-link` 接收 `{ "url": "https://example.com/" }`。本機 same-origin 限制、每分鐘最多 30 次未快取查詢、最多兩個並行、最多 256 筆短期記憶體快取。`ChatRoom/link_checks.py` 透過 SafeFetcher 做防 SSRF 的公開 HTTP GET（含每次轉址檢查），再送現有網站分析管線；不執行 JS、不登入、不操作表單。每網址最多四次 LLM 呼叫。Google 查核需配置其 key。

風險卡片列出所有原因；失敗顯示未知；未命中也不標示已安全。開啟頁面是使用者點擊，風險／未知結果會先確認。標準靜態擷取仍可能看不到動態、登入、驗證或地區限定內容。

檔案：`link_checks.py` 查訪與裁決；`link_checks.mjs` 擷取／佇列／卡片；`app.js` 訊息流程觸發；`server.py` API 與共用設定；`index.html` 查核區。測試：`uv run python -m pytest -q`、`npm --prefix extension test`、聊天室啟動後 `npm --prefix extension run test:chat`。瀏覽器 UI 測試使用模擬服務結果，實際公開網站另行 smoke test。

## 在交付前提醒（dialogue-v6）

敏感資料規則明確納入「領獎／收款驗證卻索取卡號與安全碼」，在要求提出時判斷，不等待使用者回報損失。`intervention.py` 另以保守的直接要求模式補足模型漏判：同則需含領獎、卡號、安全碼，排除 user 發言、否定及宣導引用；其餘語境仍交由 LLM 判斷。規則來源以結果 `request_guard` 記錄，證據只用已播放原文。模型服務失敗仍顯示分析失敗並暫停，不能視為安全。

`app.js` 遇到 warn 暫停自動重播，確認後可手動繼續。這是暫停 demo 播放，不代表已阻擋外部網站的表單。若已出現使用者明確表示卡片資料送出的訊息，結果 `intervention.reported_turn` 記錄回報輪次，介面改為事後提示；不能宣稱已客觀查證送出或扣款。首次示警輪次保持實際結果，不回填歷史。

回歸涵蓋 B5 第 5 則提早警告、第 8 則回報送出、正常購物／宣導反例及瀏覽器自動暫停／手動繼續。舊 session 及匯出紀錄不會重新計算；更新後請重新整理並重設案例。
