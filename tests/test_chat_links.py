import pytest

from ChatRoom.link_checks import inspect_link
from script.config import Settings


class Fetcher:
    def get(self, url):
        return {
            "url": url,
            "text": "<title>監理服務網</title><p>立即補繳罰款，否則移送。請將驗證碼告知客服。</p>",
            "redirects": [],
        }


async def test_static_fetch_reuses_pipeline_and_exposes_reasons():
    report = await inspect_link("https://fake.example", Settings(network_enabled=True), Fetcher())
    assert report["status"] == "risk"
    assert report["fetch_status"] == "static_html"
    assert report["reasons"]


async def test_fetch_failure_is_unknown_not_safe():
    class Failed:
        def get(self, url):
            raise OSError("private details")

    report = await inspect_link("https://example.com", Settings(network_enabled=True), Failed())
    assert report["status"] == "unknown"
    assert report["fetch_status"] == "unavailable"
    assert "private details" not in str(report)


async def test_local_url_is_never_fetched(monkeypatch):
    import socket

    connections = []

    def forbidden(*args, **kwargs):
        connections.append(args)
        raise AssertionError("must not connect")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    report = await inspect_link("http://127.0.0.1:8088/", Settings(network_enabled=True))
    assert report["fetch_status"] == "unavailable"
    assert connections == []


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "file:///etc/passwd", "https://user:pass@example.com"]
)
async def test_invalid_urls_rejected(url):
    with pytest.raises(ValueError):
        await inspect_link(url, Settings())
