import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from script.config import Settings
from script.llm import LLM
from script.models import PageContext
from script.vision import analyze_screenshot


def fake_client(payload):
    return SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(status="completed", output_text=json.dumps(payload))
            )
        ),
        close=AsyncMock(),
    )


def settings(**kwargs):
    defaults = {
        "api_key": "test-placeholder",
        "llm_enabled": True,
        "allow_content_upload": True,
        "audit_enabled": False,
    }
    defaults.update(kwargs)
    return Settings(**defaults)


async def test_screenshot_is_sent_as_low_detail_data_url_and_only_adds_inferred_evidence():
    client = fake_client({"finding": "suspicious", "confidence": 0.9, "reason_code": "credential_prompt"})
    screenshot = b"\xff\xd8\xffjpeg-bytes"
    result = await analyze_screenshot(
        PageContext(url="https://fake.example"), screenshot, LLM(settings(), client)
    )

    assert result.layer == "VISION"
    assert result.verdict == "suspicious"
    assert result.signals[0].grade == "inferred"
    content = client.responses.create.call_args.kwargs["input"][0]["content"]
    image = content[1]
    assert image["type"] == "input_image"
    assert image["detail"] == "low"
    assert image["image_url"] == "data:image/jpeg;base64," + base64.b64encode(screenshot).decode()
    assert client.responses.create.call_args.kwargs["store"] is False


async def test_screenshot_respects_content_upload_consent():
    client = fake_client({"finding": "clean", "confidence": 1, "reason_code": "none"})
    llm = LLM(settings(allow_content_upload=False), client)
    result = await analyze_screenshot(PageContext(url="https://example.com"), b"\xff\xd8\xffjpeg-bytes", llm)

    assert result.status == "skipped"
    client.responses.create.assert_not_called()
