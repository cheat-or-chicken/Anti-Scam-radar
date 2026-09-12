# 防詐教育 RAG API

這是以 `判決書/` 和 `詐騙手法/` 中 PDF 建立的全本機 RAG。它不是模型微調：PDF 會先被切片並由本機 Ollama embedding 模型建成 `rag_index.json`；提問時再找出相關片段，交給本機 Ollama 的 `qwen3:8b` 產生回答。

為了安全，這是「防詐教育模擬器」：可分析詐騙情境與紅旗，但不會產生可直接拿去行騙的對話腳本、付款／轉帳指示、釣魚連結或資料蒐集流程。

## 啟動

在此資料夾執行（Windows PowerShell）：

```powershell
pip install -r requirements.txt
ollama pull qwen3:8b
ollama pull nomic-embed-text
python build_index.py
```

`build_index.py` 是唯一負責更新／生成向量資料庫的程式。首次使用與 PDF 有更新時都重新執行一次：

```powershell
python build_index.py
```

> 所有模型呼叫都在本機 Ollama 執行，沒有 OpenAI API 金鑰與用量費用。首次或 PDF 更新後，請重新建立 `rag_index.json`；平時提問只會建立一個查詢向量。

## Python 程式呼叫

其他 Python 程式只需匯入一個函式：

```python
from rag_client import ask_rag

result = ask_rag("假客服詐騙有哪些警訊？")
print(result["answer"])
print(result["sources"])
```

- `rag_config.py`：集中設定 `SYSTEM_PROMPT`、`CHAT_MODEL`、`TOP_K`、切片大小等參數。
- `build_index.py`：唯一負責生成／覆蓋 `rag_index.json`。
- `rag_client.py`：對外提供 `ask_rag(question, history=None, top_k=5)`。

## 終端機對話測試

完成索引後，可直接啟動互動式虛構角色對話，以目前 `rag_config.py` 的 `SYSTEM_PROMPT` 評估多輪角色一致性：

```powershell
python chat_cli.py
```

直接輸入對角色的回覆即可。模型只輸出明確標示為虛構訓練的角色台詞；RAG 檢索來源不會顯示於終端機。可用 `/clear` 清除本次對話，或用 `/quit` 離開。此工具只將歷史保留在記憶體中，不會寫入對話紀錄檔。

## 網站串接接口

若網站想以 HTTP 呼叫，另外啟動：

```powershell
python rag_server.py
```

### `POST /api/chat`

Request body：

```json
{
  "message": "假客服詐騙有哪些可辨識的警訊？",
  "history": [
    { "role": "user", "content": "前一個問題" },
    { "role": "assistant", "content": "前一個回答" }
  ]
}
```

Response 會包含模型回答及可供前端顯示的資料來源：

```json
{
  "answer": "...",
  "sources": [{ "source": "詐騙手法/假客服.pdf", "page": 1, "score": 0.82 }],
  "safety_mode": "防詐教育模擬：不提供可執行的詐騙話術或金流操作。"
}
```

瀏覽器呼叫範例：

```js
const response = await fetch('http://127.0.0.1:8010/api/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message: userText, history })
});
const result = await response.json();
```

### `GET /health`

確認服務及索引狀態；回傳 `indexed` 和 `chunks`。

## 安全與部署

- API 金鑰只能存在後端環境變數，絕不可出現在 HTML、JavaScript bundle 或 Git。
- 正式網站請加上登入、rate limit、允許的前端來源（目前為方便本機整合而開放 CORS）。
- 回答中的來源是 RAG 實際檢索到的 PDF 與頁碼，應在 UI 顯示給使用者。
