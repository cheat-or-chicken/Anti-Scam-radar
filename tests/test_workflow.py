import json
from types import SimpleNamespace

import pytest

from script.config import Settings
from script.layers.adjudication import adjudicate
from script.llm import LLM
from script.models import PageContext, Signal, result
from script.workflow import apply_assessment, assess, diagnose


def answer(action="pause_sensitive_action", ref="E0_0"):
    return {
        "intent": "取得付款資料",
        "hypotheses": [{"kind": "scam", "explanation": "要求先付款", "supporting": [ref], "opposing": []}],
        "unresolved": ["需確認授權"],
        "change_conditions": ["官方提供授權證明"],
        "recommended_action": action,
        "action_evidence": [ref],
        "explanation": "請先確認來源",
    }


class FakeLLM:
    settings = Settings(llm_enabled=True, allow_content_upload=True, api_key="fake")
    calls = 0

    def __init__(self, output):
        self.output = output

    async def request(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(status="completed", output_text=json.dumps(self.output))


def layers():
    return [result("L3", [Signal(id="advance_fee", detail="先付款才可提領", weight=20)])]


async def test_valid_assessment_preserves_score_and_pauses_without_double_counting():
    ctx = PageContext(url="https://example.com", text="私密原文")
    report = await assess(ctx, layers(), FakeLLM(answer()))
    assert report["status"] == "ok"
    assert "私密原文" not in json.dumps(report, ensure_ascii=False)
    baseline = adjudicate(ctx, layers())
    final = apply_assessment(baseline, report)
    assert final.risk_score == baseline.risk_score
    assert "submit" in final.interrupt_triggers
    assert report["accepted_action"] == "pause_sensitive_action"


async def test_invented_references_rejected():
    report = await assess(PageContext(url="https://example.com"), layers(), FakeLLM(answer(ref="E999")))
    assert report["status"] == "error"


async def test_history_or_page_claim_cannot_alone_block_or_pause():
    ctx = PageContext(url="https://example.com", title="網站宣稱")
    report = await assess(ctx, [], FakeLLM(answer("block", "P1")))
    final = apply_assessment(adjudicate(ctx, []), report)
    assert final.display_level == "banner"
    assert final.interrupt_triggers == []
    assert report["accepted_action"] == "warn"


async def test_model_cannot_remove_existing_block():
    ctx = PageContext(url="https://example.com")
    baseline = adjudicate(ctx, layers()).model_copy(update={"display_level": "block", "risk_score": 100})
    report = await assess(ctx, layers(), FakeLLM(answer("observe")))
    final = apply_assessment(baseline, report)
    assert final.display_level == "block" and final.risk_score == 100


async def test_offline_never_calls_llm():
    llm = LLM(Settings())
    report = await assess(PageContext(url="https://example.com"), layers(), llm)
    assert report["status"] == "skipped"
    assert llm.calls == 0


async def test_diagnosis_is_candidate_and_cannot_invent_evidence():
    output = {
        "category": "interpretation",
        "evidence_ids": ["E0"],
        "explanation": "誤解用途",
        "proposed_change": "加入正常例子",
        "counterexample": "正常登入",
    }
    data = {"workflow": {"evidence": {"E0": {"source": "L3"}}}}
    diagnostic = await diagnose(data, "legitimate", FakeLLM(output))
    assert diagnostic["auto_applied"] is False
    with pytest.raises(ValueError):
        await diagnose({}, "legitimate", FakeLLM(output))


async def test_diagnosis_api_requires_confirmation_and_existing_audit(tmp_path):
    from httpx import ASGITransport, AsyncClient

    from script.server import create_app

    settings = Settings(llm_enabled=True, allow_content_upload=True, database_path=str(tmp_path / "audit.db"))
    token = "t" * 32
    async with AsyncClient(
        transport=ASGITransport(app=create_app(settings, token)),
        base_url="http://testserver",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        body = {"audit_id": "a" * 32, "confirmed_label": "scam"}
        assert (await client.post("/v1/diagnose", json=body)).status_code == 422
        assert (await client.post("/v1/diagnose", json={**body, "reviewed": True})).status_code == 404
