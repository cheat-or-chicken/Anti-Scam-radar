import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from script.config import Settings
from script.llm import LLM
from script.privacy import mask_input, mask_text


def test_requested_categories_masked_and_json_preserved():
    raw = 'alice@example.com 身分證A123456789 電話0912-345-678 password="hunter22" Bearer abcdefg123'
    cleaned = mask_text(raw)
    for secret in ["alice@", "A123456789", "0912", "hunter22", "abcdefg123"]:
        assert secret not in cleaned
    assert "sk-proj-" not in mask_text("sk-proj-" + "x" * 40)
    masked = json.loads(mask_input(json.dumps({"password": "secret", "note": raw})))
    assert masked["password"] == "[SECRET]"


async def test_sdk_receives_masked_text_but_image_remains_unchanged():
    create = AsyncMock(return_value=SimpleNamespace(status="completed"))
    client = SimpleNamespace(responses=SimpleNamespace(create=create), close=AsyncMock())
    llm = LLM(Settings(llm_enabled=True, api_key="fake"), client)
    image = "data:image/png;base64,12345678901234567890"
    await llm.request(
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "alice@example.com password=secret"},
                    {"type": "input_image", "image_url": image},
                ],
            }
        ]
    )
    payload = create.call_args.kwargs
    assert "alice@" not in payload["input"][0]["content"][0]["text"]
    assert payload["input"][0]["content"][1]["image_url"] == image
    assert payload["store"] is False
