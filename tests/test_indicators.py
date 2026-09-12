import json
from unittest.mock import patch

import httpx
import pytest

from script.brand_patterns import brand_patterns
from script.config import Settings
from script.indicators import inspect_content, inspect_indicators, registration, safe_browsing
from script.layers.adjudication import adjudicate
from script.layers.rules import verify_l1
from script.models import PageContext
from script.network import SafeFetcher
from script.server import create_app


@pytest.mark.parametrize("label", ["ftec-08", "fetc-09", "ft ec-08", "fetcetera", "ftex-08"])
def test_brand_token_boundaries(label):
    if " " in label:
        with pytest.raises(ValueError):
            PageContext(url=f"https://{label}.example.com")
        return
    signals = brand_patterns(f"https://{label}.example.com")
    assert bool(signals) == (label in {"ftec-08", "fetc-09"})


def test_reported_domain_warns_without_claiming_confirmed_fraud():
    ctx = PageContext(url="https://ftec-08.twietio.vip/")
    layer = verify_l1(ctx)
    decision = adjudicate(ctx, [layer])
    assert decision.display_level == "banner"
    assert decision.risk_score == 35
    assert not any(s.hard for s in layer.signals)
    assert "fetc.net.tw" in decision.reasons[0]


@pytest.mark.parametrize(
    "url",
    [
        "https://www.fetc.net.tw/",
        "https://css.fetc.net.tw/",
        "https://any-08.example.com/",
        "https://plain.vip/",
    ],
)
def test_official_and_unrelated_hosts_not_flagged(url):
    assert not brand_patterns(url)


def test_embedded_official_domain_still_warns():
    assert verify_l1(PageContext(url="https://fetc.net.tw.attacker.example/")).signals


@pytest.mark.parametrize("text", ["", "404 Not Found", "Checking your browser", "Verify you are human"])
def test_unreadable_content_not_clean(text):
    assert inspect_content(PageContext(url="https://example.com", text=text))[0]["status"] == "unknown"


def test_metadata_and_analytics_do_not_confirm_business_or_campaign():
    ctx = PageContext(
        url="https://example.com",
        html='<html><meta name="description" content="shop">'
        "<p>" + "購物車 聯絡我們 測試商品 " * 12 + "</p><script>G-ABC1234567</script></html>",
    )
    results = {r["indicator"]: r for r in inspect_content(ctx)}
    assert results["seo_metadata"]["facts"]["metadata_count"] == 1
    assert results["analytics_ids"]["facts"]["identifiers"] == ["G-ABC1234567"]
    assert results["analytics_ids"]["facts"]["association_verified"] is False


async def test_disabled_google_is_not_unlisted():
    settings = Settings()
    result = await safe_browsing(PageContext(url="https://example.com"), settings, SafeFetcher(settings))
    assert result["status"] == "unknown"


@pytest.mark.parametrize(
    "data,status",
    [
        ({"cacheDuration": "300s"}, "not_listed"),
        (
            {
                "cacheDuration": "300s",
                "threats": [{"url": "https://example.com", "threatTypes": ["SOCIAL_ENGINEERING"]}],
            },
            "matched",
        ),
        ({}, "unknown"),
        ({"error": "bad key"}, "unknown"),
        ({"cacheDuration": "300s", "threats": [{"threatTypes": ["NEW_UNKNOWN_TYPE"]}]}, "unknown"),
    ],
)
async def test_google_results(data, status):
    settings = Settings(
        network_enabled=True, safe_browsing_enabled=True, google_safe_browsing_api_key="secret"
    )
    with patch.object(SafeFetcher, "get", return_value={"text": json.dumps(data)}):
        result = await safe_browsing(PageContext(url="https://example.com"), settings, SafeFetcher(settings))
    assert result["status"] == status
    assert "secret" not in json.dumps(result)


async def test_rdap_dates_are_live_data_not_supplied_report():
    settings = Settings(network_enabled=True)
    data = {
        "events": [
            {"eventAction": "registration", "eventDate": "2025-12-30T00:00:00Z"},
            {"eventAction": "expiration", "eventDate": "2026-12-30T00:00:00Z"},
        ]
    }
    with patch.object(SafeFetcher, "get", return_value={"text": json.dumps(data)}):
        result = await registration(
            PageContext(url="https://sub.example.com"), settings, SafeFetcher(settings)
        )
    assert result["facts"]["registration_period_days"] == 365
    assert result["facts"]["domain"] == "example.com"


async def test_failed_fetch_discards_client_content():
    settings = Settings(network_enabled=True)
    with patch.object(SafeFetcher, "get", side_effect=RuntimeError("secret")):
        report = await inspect_indicators(
            PageContext(url="https://example.com", text="購物" * 100), settings, fetch_page=True
        )
    assert (
        next(x for x in report["indicators"] if x["indicator"] == "content_coverage")["status"] == "unknown"
    )
    assert "secret" not in json.dumps(report)


async def test_indicators_auth_and_check_allowlist():
    token = "a" * 32
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(Settings(), token)), base_url="http://testserver"
    ) as client:
        assert (await client.post("/v1/indicators", json={})).status_code == 401
        client.headers["Authorization"] = "Bearer " + token
        assert (
            await client.post(
                "/v1/indicators", json={"context": {"url": "https://example.com"}, "checks": ["shell"]}
            )
        ).status_code == 422
        r = await client.post("/v1/indicators", json={"context": {"url": "https://ftec-08.twietio.vip/"}})
        assert r.status_code == 200
        assert r.json()["indicators"][0]["status"] == "suspicious"
