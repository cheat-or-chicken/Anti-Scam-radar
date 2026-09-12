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

- 內建三例，或匯入 `*.replay.json`，以 `sender`、`channel` 呈現角色與分隔線。
- TXT 模式仍可輸入自己的回覆，雙方訊息共同累計輪次。
- 下一則／自動重播會先等待本輪API完成。暫停不取消已送出的API請求。
- 右側呈現示警、原文引用、七幕標籤、先前預測的核對與首次示警輪次。
- 案例名稱只供顯示，後端只讀allowlist訊息欄位，不讀檔名、標註或未來訊息。
- 對話目前以完整已見前綴加上一輪判斷維持脈絡，最多300則；尚未做長對話摘要壓縮。
- 逐輪log存在 `var/dialogue/`（不提交Git），畫面亦可匯出分析JSON。
- API或引用驗證失敗顯示analysis_error，不能當作正常或沒有誤報。
- 網站調查API尚未串接；示例域名與附件不會被宣稱為已查證。

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
