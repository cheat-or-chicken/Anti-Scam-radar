"""本機聊天室與 JSON API 伺服器。執行：python server.py"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from ChatRoom.detector import Detector  # noqa: E402
from ChatRoom.link_checks import check_link  # noqa: E402

# Share the existing local API configuration; never expose the key to browser code.
from script.config import Settings  # noqa: E402

if not os.getenv("OPENAI_API_KEY"):
    configured_key = Settings.load().api_key.get_secret_value()
    if configured_key:
        os.environ["OPENAI_API_KEY"] = configured_key
DETECTOR = Detector()
SAMPLES = {p.name: p for p in (ROOT.parent / "data/reconstructed").glob("*.replay.json")}
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
    HISTORY_FILE.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")


class ChatHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

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
        if request.path == "/api/detector":
            self.send_json({"configured": bool(os.getenv("OPENAI_API_KEY")), "model": DETECTOR.model})
            return
        if request.path == "/api/samples":
            self.send_json({"samples": sorted(SAMPLES)})
            return
        if request.path == "/api/sample":
            name = parse_qs(request.query).get("name", [""])[0]
            if name not in SAMPLES:
                self.send_json({"error": "Unknown sample"}, HTTPStatus.NOT_FOUND)
                return
            data = json.loads(SAMPLES[name].read_text())
            self.send_json(data)
            return
        if request.path == "/api/chat":
            messages = load_messages()
            requested_counterpart = parse_qs(request.query).get("counterpart", [""])[0]
            if requested_counterpart:
                messages = [
                    message for message in messages if message.get("counterpart") == requested_counterpart
                ]
            self.send_json(
                {
                    "counterpart": requested_counterpart or None,
                    "messages": messages,
                    "count": len(messages),
                }
            )
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/api/check-link":
            parsed_host = urlparse("http://" + self.headers.get("Host", "")).hostname
            origin = self.headers.get("Origin")
            if parsed_host not in {"localhost", "127.0.0.1"} or (
                origin and urlparse(origin).netloc != self.headers.get("Host")
            ):
                self.send_json({"error": "Origin not allowed"}, HTTPStatus.FORBIDDEN)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 12000:
                    raise ValueError("Invalid payload size")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict) or not isinstance(data.get("url"), str):
                    raise ValueError("Expected URL")
                self.send_json(check_link(data["url"]))
            except BlockingIOError:
                self.send_json({"error": "網址檢查忙碌中，請稍後重試"}, HTTPStatus.TOO_MANY_REQUESTS)
            except (ValueError, TypeError):
                self.send_json({"error": "網址格式不支援"}, HTTPStatus.BAD_REQUEST)
            except Exception:
                self.send_json({"error": "網址檢查未完成，不代表安全"}, HTTPStatus.BAD_GATEWAY)
            return
        if self.path in {"/api/sessions", "/api/analyze"}:
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                self.send_json({"error": "Origin not allowed"}, HTTPStatus.FORBIDDEN)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 20000:
                    raise ValueError("Request too large")
                data = json.loads(self.rfile.read(length) or b"{}")
                if self.path == "/api/sessions":
                    result = {"session_id": DETECTOR.create_session()}
                else:
                    result = DETECTOR.analyze(data["session_id"], data["message"])
                self.send_json(result)
            except (ValueError, KeyError, TypeError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception:
                self.send_json({"error": "分析服務失敗；不能視為安全"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
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
    port = int(os.getenv("PORT", "8000"))
    print(f"聊天室已啟動：http://localhost:{port}", flush=True)
    print(f"完整對話 API：http://localhost:{port}/api/chat")
    ThreadingHTTPServer(("127.0.0.1", port), ChatHandler).serve_forever()
