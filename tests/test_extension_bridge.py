import httpx
import pytest

from script.blocklist import Blocklist, digit_skeleton, verify_blocklist
from script.config import Settings
from script.models import PageContext
from script.server import create_app

TOKEN = "test-pairing-token-" + "a" * 32


def test_list_boundaries_and_digit_variants():
    data = {
        "domains": {"pages.dev": {"s": ["NPA"]}, "bad.pages.dev": {"s": ["NPA"]}, "evil.com": {"s": ["NPA"]}},
        "digitSkeletons": {"pay#.com": ["pay1.com", "pay2.com"]},
    }
    db = Blocklist(data)
    assert not db.check("https://good.pages.dev")["matched"]
    assert db.check("https://a.bad.pages.dev")["matched"]
    assert db.check("https://sub.evil.com")["matched"]
    assert db.check("https://pay3.com")["kind"] == "similar"
    assert digit_skeleton("123.com") is None
    assert verify_blocklist(PageContext(url="https://example.com")).status == "ok"


@pytest.fixture
def app():
    return create_app(Settings(audit_enabled=False), TOKEN)


async def test_backend_pairing_origin_and_validation(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765"
    ) as client:
        assert (await client.get("/health")).status_code == 200
        assert (
            await client.post("/v1/analyze", json={"context": {"url": "https://example.com"}})
        ).status_code == 401
        headers = {"Authorization": "Bearer " + TOKEN}
        assert (
            await client.post("/v1/analyze", headers={**headers, "Origin": "https://evil.example"}, json={})
        ).status_code == 403
        assert (
            await client.post("/v1/analyze", headers=headers, json={"context": {"url": "file:///etc/passwd"}})
        ).status_code == 422
        assert (await client.post("/v1/analyze", headers=headers, content="x" * 1000001)).status_code == 413
        response = await client.post(
            "/v1/analyze",
            headers=headers,
            json={
                "context": {
                    "url": "https://example.com",
                    "network_trace": [
                        {"url": "https://leak.example", "observed": True, "sensitive_data": True}
                    ],
                }
            },
        )
        assert response.status_code == 200
        assert response.json()["decision"]["risk_score"] == 0
        assert len(response.json()["layers"]) == 19


async def test_manual_url_network_disabled(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765"
    ) as client:
        response = await client.post(
            "/v1/check-url",
            headers={"Authorization": "Bearer " + TOKEN},
            json={"url": "https://example.com/?token=PRIVATE", "fetch_page": True},
        )
        assert response.status_code == 200
        assert response.json()["fetch_status"] == "network_disabled"
        assert "PRIVATE" not in response.text


async def test_request_can_disable_llm(monkeypatch):
    from script import server

    seen = []
    original = server.analyze

    async def capture(ctx, settings):
        seen.append(settings.llm_enabled)
        return await original(ctx, settings.model_copy(update={"llm_enabled": False}))

    monkeypatch.setattr(server, "analyze", capture)
    app = create_app(Settings(llm_enabled=True, api_key="test-key", audit_enabled=False), TOKEN)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.post(
            "/v1/analyze",
            headers={"Authorization": "Bearer " + TOKEN},
            json={"context": {"url": "https://example.com"}, "include_llm": False},
        )
        assert response.status_code == 200 and seen == [False]


async def test_pairing_rate_limit(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        statuses = [
            (
                await client.post(
                    "/v1/analyze",
                    headers={"Authorization": "Bearer " + TOKEN},
                    json={"context": {"url": "https://example.com"}},
                )
            ).status_code
            for _ in range(13)
        ]
        assert statuses[-1] == 429


def test_importer_preserves_public_ip_and_rejects_shared_suffix(tmp_path):
    import json

    from script.build_blocklist import build

    (tmp_path / "NPA_WEBURL.csv").write_text(
        "網站名稱,網址,統計結束日期\npublic,8.8.8.8,2026/01/01\nprivate,127.0.0.1,2026/01/01\nshared,pages.dev,2026/01/01\ntenant,bad.pages.dev,2026/01/01\n"
    )
    (tmp_path / "通報TWNIC詐騙網址彙整表.json").write_text(json.dumps([]))
    data = build(tmp_path)
    assert set(data["domains"]) == {"8.8.8.8", "bad.pages.dev"}


async def test_snapshot_populates_rdap_and_reuses_cache(monkeypatch):
    from unittest.mock import AsyncMock

    from script.tools import VerificationTools

    lookup = AsyncMock(return_value={"status": "ok", "domain_age_days": 200})
    monkeypatch.setattr(VerificationTools, "call", lookup)
    app = create_app(Settings(network_enabled=True, audit_enabled=False), "a" * 32)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": "Bearer " + "a" * 32},
    ) as client:
        for _ in range(2):
            r = await client.post(
                "/v1/analyze", json={"context": {"url": "https://example.com", "dom_collected": True}}
            )
            assert r.status_code == 200
            layers = {layer["layer"]: layer for layer in r.json()["layers"]}
            assert layers["L5"]["status"] == "ok"
            assert layers["L15"]["status"] == "ok"
            assert layers["L4"]["status"] == "ok"
            assert layers["L7"]["status"] == "skipped"
    assert lookup.await_count == 1
