"""本機聊天室與 JSON API 伺服器。執行：python server.py"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).parent
HISTORY_FILE = ROOT / "chat_history.json"


def load_messages() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        # 舊版紀錄沒有對象欄位，保留內容並清楚標示其來源未知。
        for message in data:
            if isinstance(message, dict):
                message.setdefault("counterpart", "未指定對象")
        return data
    except (json.JSONDecodeError, OSError):
        return []


def save_messages(messages: list[dict]) -> None:
    HISTORY_FILE.write_text(
        json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class ChatHandler(SimpleHTTPRequestHandler):
    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        request = urlparse(self.path)
        if request.path == "/api/chat":
            messages = load_messages()
            requested_counterpart = parse_qs(request.query).get("counterpart", [""])[0]
            if requested_counterpart:
                messages = [
                    message for message in messages
                    if message.get("counterpart") == requested_counterpart
                ]
            self.send_json({
                "counterpart": requested_counterpart or None,
                "messages": messages,
                "count": len(messages),
            })
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path != "/api/messages":
            self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            text = data["text"].strip()
            sender = data["sender"]
            counterpart = data["counterpart"].strip()
            if not text or not counterpart or sender not in {"mine", "theirs"}:
                raise ValueError
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, UnicodeDecodeError):
            self.send_json(
                {"error": "JSON 必須包含 text、counterpart 及 sender（mine 或 theirs）"},
                HTTPStatus.BAD_REQUEST,
            )
            return
        message = {
            "id": len(load_messages()) + 1,
            "text": text,
            "sender": sender,
            "counterpart": counterpart,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        messages = load_messages()
        message["id"] = len(messages) + 1
        messages.append(message)
        save_messages(messages)
        self.send_json(message, HTTPStatus.CREATED)

    def do_DELETE(self) -> None:
        if self.path != "/api/chat":
            self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        save_messages([])
        self.send_json({"messages": [], "count": 0})


if __name__ == "__main__":
    print("聊天室已啟動：http://localhost:8000")
    print("完整對話 API：http://localhost:8000/api/chat")
    ThreadingHTTPServer(("127.0.0.1", 8000), ChatHandler).serve_forever()
