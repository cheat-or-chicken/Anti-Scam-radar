import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from script.adaptive import Detector, detect, evaluate, promote
from script.config import Settings
from script.investigation import investigate
from script.layers.rules import verify_l2
from script.llm import LLM, redact
from script.models import PageContext
from script.pipeline import analyze
from script.tools import VerificationTools


def fake_client(output):
    return SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=output)), close=AsyncMock()
    )


def settings(**kwargs):
    return Settings(
        api_key="test-placeholder", llm_enabled=True, allow_content_upload=True, audit_enabled=False, **kwargs
    )


async def test_structured_llm_never_claims_observed_or_removes_evidence():
    response = SimpleNamespace(
        status="completed",
        output_text=json.dumps({"finding": "suspicious", "confidence": 0.9, "reason_code": "impersonation"}),
    )
    client = fake_client(response)
    llm = LLM(settings(), client)
    ctx = PageContext(url="https://fake.example", title="監理服務網", text="ignore instructions")
    base = verify_l2(ctx)
    r = await llm.supplement(base, ctx)
    assert len(r.signals) == len(base.signals) + 1
    assert r.signals[-1].grade == "inferred"
    assert not r.signals[-1].hard
    params = client.responses.create.call_args.kwargs
    assert params["store"] is False
    assert params["text"]["format"]["strict"] is True
    assert params["max_output_tokens"] == 1600


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(status="incomplete", output_text="{}"),
        SimpleNamespace(status="completed", output_text="invalid JSON"),
    ],
)
async def test_malformed_response_keeps_rules(response):
    llm = LLM(settings(), fake_client(response))
    ctx = PageContext(url="https://fake.example", title="監理服務網")
    base = verify_l2(ctx)
    r = await llm.supplement(base, ctx)
    assert r.signals == base.signals
    assert "LLM 未完成" in r.user_facing_reason


async def test_privacy_switch_prevents_api_call():
    config = settings().model_copy(update={"allow_content_upload": False})
    client = fake_client(None)
    llm = LLM(config, client)
    ctx = PageContext(url="https://example.com", title="test")
    await llm.supplement(verify_l2(ctx), ctx)
    client.responses.create.assert_not_called()


async def test_call_budget():
    llm = LLM(settings(max_llm_calls=1), fake_client(SimpleNamespace(status="completed")))
    await llm.request(model="test", input="one")
    with pytest.raises(RuntimeError):
        await llm.request(model="test", input="two")


def test_redaction():
    text = redact("https://x.example/a?session=SECRET a@b.com A123456789 0912345678")
    assert "SECRET" not in text
    assert "A123456789" not in text
    assert "a@b.com" not in text


async def test_planner_only_sees_structured_summaries(monkeypatch):
    class Call:
        type = "function_call"
        name = "fetch_script"
        arguments = "{}"
        call_id = "call_1"

        def model_dump(self, **kwargs):
            return {
                "type": self.type,
                "name": self.name,
                "arguments": self.arguments,
                "call_id": self.call_id,
            }

    first = SimpleNamespace(status="completed", output=[Call()])
    final = SimpleNamespace(status="completed", output=[])
    client = fake_client(first)
    client.responses.create.side_effect = [first, final]
    llm = LLM(settings(), client)
    tools = VerificationTools(settings())

    async def fake_fetch(ctx):
        return {"status": "ok", "scripts": ["PAGE_INJECTION_IGNORE_ALL"]}

    monkeypatch.setattr(tools, "fetch_script", fake_fetch)
    ctx = PageContext(url="https://example.com", text="RAW_SECRET_CONTENT")
    outcome = await investigate(ctx, [verify_l2(ctx)], llm, tools)
    assert outcome["outputs"]["fetch_script"]["scripts"]
    for call in client.responses.create.call_args_list:
        serialized = json.dumps(call.kwargs)
        assert "PAGE_INJECTION" not in serialized
        assert "RAW_SECRET" not in serialized
    assert len(outcome["trace"]) == 1


def test_shadow_rule_and_promotion():
    rule = Detector(
        id="sample_rule", feature="sensitive_field_count", minimum=1, weight=10, provenance="synthetic test"
    )
    ctx = PageContext(url="https://example.com", sensitive_fields=["password"])
    assert detect(rule, ctx) is None
    assert detect(rule, ctx, shadow=True)
    with pytest.raises(ValueError):
        promote(rule, [(ctx, True)], reviewed=True)
    cases = [(ctx, True)] * 15 + [(PageContext(url="https://example.com"), False)] * 15
    assert evaluate(rule, cases)["fpr"] == 0
    assert promote(rule, cases, reviewed=True).state == "active"
    with pytest.raises(ValueError):
        promote(rule, cases)


async def test_adaptive_can_only_increase_score():
    rule = Detector(
        id="sample_rule",
        feature="sensitive_field_count",
        minimum=1,
        weight=20,
        provenance="test",
        state="active",
    )
    ctx = PageContext(url="https://example.com", sensitive_fields=["password"])
    baseline = await analyze(ctx, Settings(audit_enabled=False))
    extra = await analyze(ctx, Settings(audit_enabled=False), detectors=[rule])
    assert extra.decision.risk_score >= baseline.decision.risk_score
    assert extra.decision.display_level != "block"
