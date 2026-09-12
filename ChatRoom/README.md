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
