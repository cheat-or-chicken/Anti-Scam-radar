import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from script.config import Settings
from script.llm import LLM
from script.models import PageContext
from script.server import create_app
from script.site_checks import analyze_semantics, verify_brand


def response(data, output=None):
    return SimpleNamespace(status="completed", output_text=json.dumps(data), output=output or [])


def llm(*responses):
    client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(side_effect=responses)), close=AsyncMock()
    )
    return LLM(
        Settings(api_key="test", llm_enabled=True, allow_content_upload=True, network_enabled=True), client
    )


PAGE = PageContext(url="https://7-11.com.tw.evil.example", text="我們是台灣 7-ELEVEN 官方網站")
CLAIM = dict(brand="7-ELEVEN", region="台灣", self_claim=True, confidence=0.95, quote=PAGE.text)
SOURCES = [
    {
        "type": "web_search_call",
        "status": "completed",
        "action": {"sources": [{"url": "https://www.7-11.com.tw/"}]},
    }
]
SELECT = dict(source_indexes=[0], confidence=0.9, ambiguous=False)


@pytest.mark.parametrize(
    "url,expected",
    [
        (PAGE.url, "mismatch"),
        ("https://www.7-11.com.tw/", "match"),
        ("http://www.7-11.com.tw/", "mismatch"),
        ("https://other.7-11.com.tw/", "mismatch"),
    ],
)
async def test_brand_uses_search_and_exact_https_host(url, expected):
    model = llm(response(CLAIM), response("官方網站", SOURCES), response(SELECT))
    result = await verify_brand(PAGE.model_copy(update={"url": url}), model)
    assert result["match"] == expected
    search = model.client.responses.create.call_args_list[1].kwargs
    assert search["tool_choice"] == "required"
    assert search["include"] == ["web_search_call.action.sources"]
    assert "evil.example" not in search["input"]
    assert all(c.kwargs["store"] is False for c in model.client.responses.create.call_args_list)


@pytest.mark.parametrize(
    "selection",
    [
        dict(SELECT, source_indexes=[1]),
        dict(SELECT, source_indexes=[-1]),
        dict(SELECT, ambiguous=True),
        dict(SELECT, confidence=0.5),
    ],
)
async def test_unreliable_sources_unknown(selection):
    model = llm(response(CLAIM), response("官方網站", SOURCES), response(selection))
    assert (await verify_brand(PAGE, model))["status"] == "unknown"


async def test_no_actual_search_sources_never_accepts_model_url():
    model = llm(response(CLAIM), response("官方網站 https://www.7-11.com.tw/"))
    assert (await verify_brand(PAGE, model))["reason"] == "no_search_sources"


@pytest.mark.parametrize("claim", [dict(CLAIM, self_claim=False), dict(CLAIM, quote="不存在的文字")])
async def test_no_claim_no_search(claim):
    model = llm(response(claim))
    assert (await verify_brand(PAGE, model))["status"] == "unknown"
    assert model.calls == 1


async def test_semantic_evidence_and_html_extraction():
    model = llm(
        response(
            dict(
                verdict="suspicious",
                confidence=0.9,
                findings=[dict(category="credential_handoff", quote="請把 OTP 交給客服")],
            )
        )
    )
    result = await analyze_semantics(PageContext(url=PAGE.url, html="<p>請把 OTP 交給客服</p>"), model)
    assert result["verdict"] == "suspicious"
    assert result["evidence_grade"] == "inferred"
    assert "tools" not in model.client.responses.create.call_args.kwargs


@pytest.mark.parametrize(
    "verdict,findings",
    [
        ("suspicious", []),
        ("suspicious", [dict(category="urgent_payment", quote="虛構")]),
        ("clean", [dict(category="impersonation", quote=PAGE.text)]),
    ],
)
async def test_semantic_rejects_unsubstantiated_result(verdict, findings):
    model = llm(response(dict(verdict=verdict, confidence=0.9, findings=findings)))
    assert (await analyze_semantics(PAGE, model))["status"] == "unknown"


async def test_clean_is_not_safety_guarantee():
    model = llm(response(dict(verdict="clean", confidence=0.9, findings=[])))
    result = await analyze_semantics(PAGE, model)
    assert result["verdict"] == "clean"
    assert "不代表網站安全" in result["reason"]


@pytest.mark.parametrize("check", [verify_brand, analyze_semantics])
@pytest.mark.parametrize("setting", ["llm_enabled", "allow_content_upload"])
async def test_disabled_no_upload(check, setting):
    model = llm()
    setattr(model.settings, setting, False)
    assert (await check(PAGE, model))["status"] == "unknown"
    model.client.responses.create.assert_not_called()


async def test_network_gate_and_call_budget():
    model = llm()
    model.settings.network_enabled = False
    assert (await verify_brand(PAGE, model))["reason"] == "web_search_disabled"
    assert model.calls == 0
    model.settings.network_enabled = True
    model.settings.max_llm_calls = 0
    assert (await verify_brand(PAGE, model))["status"] == "unknown"


@pytest.mark.parametrize("check", [verify_brand, analyze_semantics])
async def test_error_does_not_leak_secret(check):
    model = llm(RuntimeError("secret-api-key"))
    assert "secret" not in json.dumps(await check(PAGE, model))


@pytest.mark.parametrize("path", ["verify-brand", "analyze-semantics"])
async def test_endpoints_authenticated_and_validate(path):
    token = "a" * 32
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(Settings(), token)), base_url="http://testserver"
    ) as client:
        assert (await client.post("/v1/" + path, json={})).status_code == 401
        client.headers["Authorization"] = "Bearer " + token
        assert (await client.post("/v1/" + path, json={})).status_code == 422
        result = await client.post("/v1/" + path, json={"context": PAGE.model_dump()})
        assert result.status_code == 200
        assert result.json()["reason"] == "llm_disabled_or_missing_key"


@pytest.mark.parametrize(
    "redirect,expected", [("https://www.7-11.com.tw/", "match"), ("https://7-11.com.tw/", "unknown")]
)
async def test_www_alias_requires_observed_redirect(monkeypatch, redirect, expected):
    sources = [
        {
            "type": "web_search_call",
            "status": "completed",
            "action": {"sources": [{"url": "https://7-11.com.tw/"}]},
        }
    ]
    monkeypatch.setattr("script.site_checks.SafeFetcher.get", lambda self, url: {"url": redirect})
    model = llm(response(CLAIM), response("官方網站", sources), response(SELECT))
    result = await verify_brand(PAGE.model_copy(update={"url": "https://www.7-11.com.tw/"}), model)
    assert result["match"] == expected
