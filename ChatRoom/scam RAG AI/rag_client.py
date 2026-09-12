"""給其他 Python 程式使用的簡單 RAG 呼叫函式。"""
from __future__ import annotations

import json
import math

from build_index import create_embeddings
from ollama_api import chat
from rag_config import (
    CHAT_MODEL,
    INDEX_PATH,
    MAX_HISTORY_MESSAGES,
    SYSTEM_PROMPT,
    TOP_K,
)


# 此護欄優先於 rag_config.py 的可調整 prompt，避免測試工具被用於實際詐騙。
RUNTIME_SAFETY_GUARDRAIL = """

""".strip()

ROLEPLAY_STYLE ="""
只輸出 1 到 3 句自然、簡短的角色台詞，不輸出分析、教學、標題、來源或行動清單。

劇情必須採取「漸進式發展」，不要在開場或前幾輪直接表現出明顯的詐騙特徵。

若尚未有對話歷史：
- 先以自然、日常、低風險的方式問候或開啟話題。
- 不要一開始就提及異常、帳戶問題、付款、驗證、獎金、緊急事件或其他高風險要求。
- 先建立角色身分、對話背景與自然互動，再逐步引入情境。

隨著對話發展，按照「建立接觸 → 建立信任 → 建立情境 → 合理化需求 → 試探反應 → 逐步提高要求 → 高風險行動」的節奏推進。

前期：
- 以一般資訊、關心、閒聊或角色本身的合理目的為主。
- 避免過度熱情、過度正式、刻意製造緊張感。
- 不要急著要求使用者做任何敏感操作。

中期：
- 根據使用者的回應逐步增加情境細節。
- 可以出現輕微的權威感、利益誘因、時間因素或情緒壓力，但應該具有合理的劇情鋪墊。
- 先觀察使用者是否接受情境，再逐步增加要求。

後期：
- 當前面的信任與情境已經建立後，才逐漸出現較高風險的要求。
- 要求的強度必須符合目前劇本階段，不應突然跳到最終目的。
- 若使用者產生懷疑，不要立即暴露劇本，而應根據既有情境自然回應。

每一輪都必須延續前面的情境，並根據使用者的反應決定下一步。
不要跳過中間階段，不要在短時間內完成整個詐騙流程。
""".strip()


def _load_index() -> dict:
    if not INDEX_PATH.exists():
        raise FileNotFoundError("尚未建立 rag_index.json；請先執行：python build_index.py")
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    length = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return sum(a * b for a, b in zip(left, right)) / length if length else 0.0


def retrieve(question: str, top_k: int = TOP_K) -> list[dict]:
    """取得最相關的來源片段；可供需自行組 prompt 的程式使用。"""
    index = _load_index()
    query_embedding = create_embeddings([question])[0]
    candidates = [(_cosine_similarity(query_embedding, chunk["embedding"]), chunk) for chunk in index["chunks"]]
    return [
        {"source": chunk["source"], "page": chunk["page"], "text": chunk["text"], "score": round(score, 4)}
        for score, chunk in sorted(candidates, key=lambda item: item[0], reverse=True)[:top_k]
    ]


def _ask(question: str, history: list[dict] | None, top_k: int, instructions: str) -> dict:
    question = question.strip()
    if not question:
        raise ValueError("question 不可為空白")
    sources = retrieve(question, top_k)
    context = "\n\n".join(f"[來源：{item['source']}，第 {item['page']} 頁]\n{item['text']}" for item in sources)
    previous = "\n".join(
        f"{item.get('role', 'user')}: {str(item.get('content', ''))[:500]}"
        for item in (history or [])[-MAX_HISTORY_MESSAGES:]
        if item.get("role") in {"user", "assistant"}
    )
    answer = chat(
        CHAT_MODEL,
        f"{RUNTIME_SAFETY_GUARDRAIL}\n\n目前設定的助理 prompt：\n{instructions}",
        f"參考資料：\n{context}\n\n先前對話：\n{previous or '（無）'}\n\n使用者問題：{question}",
    )
    return {
        "answer": answer,
        "sources": [{key: item[key] for key in ("source", "page", "score")} for item in sources],
    }


def ask_rag(question: str, history: list[dict] | None = None, top_k: int = TOP_K) -> dict:
    """一般防詐問答：回傳 answer、sources 與 safety_mode。"""
    return _ask(question, history, top_k, SYSTEM_PROMPT)


def roleplay_rag(user_reply: str, history: list[dict] | None = None, top_k: int = TOP_K) -> dict:
    """純虛構角色台詞模式；保留 RAG 與安全護欄。"""
    return _ask(user_reply, history, top_k, f"{SYSTEM_PROMPT}\n\n{ROLEPLAY_STYLE}")
