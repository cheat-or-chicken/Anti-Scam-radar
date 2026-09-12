import threading
from http.server import ThreadingHTTPServer

import httpx
import pytest

from script.config import Settings
from script.demo_server import Handler
from script.domains import parse_url
from script.network import SafeFetcher


def test_demo_port_exception_is_only_loopback():
    assert parse_url("http://127.0.0.1:8088/traffic.html").port == 8088
    for url in ["http://example.com:8088/", "http://127.0.0.1:8089/", "https://127.0.0.1:8088/"]:
        with pytest.raises(ValueError):
            parse_url(url)
    # Accepting a local page snapshot must not bypass the fetcher's SSRF protection.
    with pytest.raises(Exception):
        SafeFetcher(Settings(network_enabled=True)).get("http://127.0.0.1:8088/")


def test_demo_serves_only_assets_and_rejects_submissions():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}") as client:
            for page in [
                "/",
                "/traffic.html",
                "/investment.html",
                "/support.html",
                "/otp.html",
                "/prize.html",
            ]:
                response = client.get(page)
                assert response.status_code == 200
                assert "教學模擬" in response.text
                assert "form-action 'none'" in response.headers["Content-Security-Policy"]
                assert "connect-src 'none'" in response.headers["Content-Security-Policy"]
            assert client.post("/otp.html", data={"otp": "DEMO_VALUE"}).status_code == 405
            assert client.get("/config/config.local.json").status_code == 404
            assert client.get("/demo.js").status_code == 200
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
