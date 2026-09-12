import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from script.config import Settings
from script.layers.adjudication import adjudicate
from script.layers.code_review import verify_l7
from script.llm import LLM
from script.models import PageContext
from script.pipeline import analyze


def reviewer(payload):
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(status="completed", output_text=json.dumps(payload))
            )
        ),
        close=AsyncMock(),
    )
    return LLM(Settings(api_key="fake-key", llm_enabled=True, allow_content_upload=True), client)


async def test_code_review_feedback_is_inferred_and_never_executes():
    llm = reviewer(
        {
            "verdict": "suspicious",
            "confidence": 0.9,
            "findings": [{"script_index": 0, "concern": "keystroke_collection"}],
        }
    )
    ctx = PageContext(url="https://example.com", scripts=["throw new Error('DO NOT EXECUTE');"])
    result = await verify_l7(ctx, llm)
    assert result.verdict == "suspicious"
    assert "scripts[0]" in result.feedback[0]
    assert all(s.grade == "inferred" and not s.hard for s in result.signals)
    assert adjudicate(ctx, [result]).display_level == "banner"
    assert "tools" not in llm.client.responses.create.call_args.kwargs


async def test_normal_review_returns_useful_feedback():
    llm = reviewer({"verdict": "clean", "confidence": 0.9, "findings": []})
    result = await verify_l7(PageContext(url="https://example.com", scripts=["const sum = 1 + 2;"]), llm)
    assert result.verdict == "clean"
    assert result.feedback and not result.signals


@pytest.mark.parametrize("scripts,upload", [([], True), (["const a=1"], False)])
async def test_missing_input_or_consent_makes_no_call(scripts, upload):
    llm = reviewer({})
    llm.settings.allow_content_upload = upload
    result = await verify_l7(PageContext(url="https://example.com", scripts=scripts), llm)
    assert result.verdict == "unknown"
    llm.client.responses.create.assert_not_called()


async def test_invalid_reference_rejected():
    llm = reviewer(
        {
            "verdict": "suspicious",
            "confidence": 0.9,
            "findings": [{"script_index": 5, "concern": "sensitive_transfer"}],
        }
    )
    result = await verify_l7(PageContext(url="https://example.com", scripts=["code"]), llm)
    assert result.status == "error" and not result.signals


async def test_pipeline_prioritizes_l7(monkeypatch):
    calls = []

    async def fake_request(self, **kwargs):
        calls.append(kwargs)
        self.calls += 1
        return SimpleNamespace(
            status="completed",
            output_text=json.dumps({"verdict": "clean", "confidence": 0.9, "findings": []}),
        )

    monkeypatch.setattr(LLM, "request", fake_request)
    result = await analyze(
        PageContext(url="https://example.com", scripts=["const sum=1+2"]),
        Settings(
            api_key="fake", llm_enabled=True, allow_content_upload=True, audit_enabled=False, max_llm_calls=1
        ),
    )
    assert result.layers[7].verdict == "clean"
    assert len(calls) == 1
    assert calls[0]["text"]["format"]["name"] == "code_review"
