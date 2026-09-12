"""Loopback static demo server; no form submission or user data storage."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent / "demo"
FILES = {
    "index.html",
    "traffic.html",
    "investment.html",
    "support.html",
    "otp.html",
    "prize.html",
    "demo.css",
    "demo.js",
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        name = urlsplit(self.path).path.lstrip("/") or "index.html"
        if name not in FILES:
            self.send_error(404)
            return
        data = (ROOT / name).read_bytes()
        self.send_response(200)
        kind = (
            "text/css"
            if name.endswith(".css")
            else "text/javascript"
            if name.endswith(".js")
            else "text/html"
        )
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'none'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        self.send_error(405, "Demo forms never submit")

    def log_message(self, format, *args):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8088), Handler)
    print("RADAR LAB: http://127.0.0.1:8088/ — Ctrl+C to stop", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
