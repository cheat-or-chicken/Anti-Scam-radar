"""僅負責與本機 Ollama REST API 通訊。"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class OllamaAPIError(RuntimeError):
    pass


def _post(path: str, payload: dict) -> dict:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise OllamaAPIError(f"Ollama API {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise OllamaAPIError(f"無法連線至本機 Ollama：{error.reason}") from error
    return body


def embed(model: str, texts: list[str]) -> list[list[float]]:
    """使用本機 Ollama embedding 模型將文字轉為向量。"""
    body = _post("/api/embed", {"model": model, "input": texts})
    embeddings = body.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        raise OllamaAPIError(f"Ollama embedding 回應格式不正確：{body}")
    if not all(isinstance(vector, list) for vector in embeddings):
        raise OllamaAPIError(f"Ollama embedding 回應格式不正確：{body}")
    return embeddings


def chat(model: str, system_prompt: str, user_prompt: str) -> str:
    """以本機 Ollama 對話 API 產生一次非串流回應。"""
    body = _post("/api/chat", {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    })

    content = body.get("message", {}).get("content")
    if not isinstance(content, str):
        raise OllamaAPIError(f"Ollama 回應格式不正確：{body}")
    return content.strip()
