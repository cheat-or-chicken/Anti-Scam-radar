"""Loopback-only HTTP bridge for the unpacked Chrome extension."""

import asyncio
import base64
import binascii
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from script.config import Settings
from script.models import PageContext
from script.pipeline import analyze
from script.vision import MAX_SCREENSHOT_BYTES, image_mime_type

MAX_REQUEST_BYTES = 8_000_000


def decode_extension_payload(payload: Any) -> tuple[PageContext, bytes]:
    """Validate the extension payload before it can reach the LLM or audit store."""
    if not isinstance(payload, dict) or set(payload) != {"context", "screenshot"}:
        raise ValueError("expected context and screenshot")
    if not isinstance(payload["screenshot"], str):
        raise ValueError("expected base64 screenshot")
    if len(payload["screenshot"]) > MAX_SCREENSHOT_BYTES * 4 // 3 + 8:
        raise ValueError("screenshot exceeds 5 MB")
    try:
        screenshot = base64.b64decode(payload["screenshot"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid screenshot encoding") from exc
    if len(screenshot) > MAX_SCREENSHOT_BYTES or image_mime_type(screenshot) is None:
        raise ValueError("expected a PNG or JPEG screenshot up to 5 MB")
    return PageContext.model_validate(payload["context"]), screenshot


def serve(settings: Settings, port: int = 8765) -> None:
    """Run an extension bridge bound only to this computer's loopback interface."""

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status: int, body: dict) -> None:
            encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self) -> None:
            if self.path == "/health":
                self.send_json(200, {"status": "ok"})
            else:
                self.send_json(404, {"error": "not_found"})

        def do_POST(self) -> None:
            if self.path != "/analyze":
                self.send_json(404, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_REQUEST_BYTES:
                    raise ValueError("request is too large")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                context, screenshot = decode_extension_payload(payload)
                outcome = asyncio.run(analyze(context, settings, screenshot=screenshot))
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
                self.send_json(400, {"error": "invalid_request"})
                return
            except Exception:
                self.send_json(500, {"error": "analysis_failed"})
                return
            self.send_json(200, outcome.model_dump())

        def log_message(self, _format: str, *_args: object) -> None:
            # URLs and page content must not be emitted into console history.
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Anti-Scam Radar extension bridge listening on http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
