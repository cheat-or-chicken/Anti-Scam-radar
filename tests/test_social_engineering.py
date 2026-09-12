import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from script.config import Settings
from script.layers.adjudication import adjudicate
from script.layers.rules import verify_l3
from script.llm import LLM
from script.models import LayerResult, PageContext, Signal


@pytest.mark.parametrize(
    "text,expected",
    [
        ("您的裝置感染病毒，請立即下載修復工具。", "scareware_pressure"),
        ("完成真人驗證，按 Win+R 再貼上指令。", "fake_verification_command"),
        ("要提領資金，請先支付保證金。", "advance_fee_request"),
        ("防詐提醒：不要先支付保證金才能提領。", None),
        ("正常會員登入，請自行輸入驗證碼。", None),
        ("公司提供遠端工作，請閱讀職缺說明。", None),
    ],
)
def test_semantic_combinations(text, expected):
    ctx = PageContext(url="https://example.com", text=text)
    result = verify_l3(ctx)
    assert bool(result.signals) == bool(expected)
    if expected:
        assert result.signals[0].id == expected
        assert adjudicate(ctx, [result]).category == "話術詐騙疑慮"


def test_small_warning_is_visible_even_on_trusted_host():
    layer = LayerResult(layer="L9", signals=[Signal(id="locale_inconsistency", detail="test", weight=5)])
    for url in ["https://example.com", "https://www.mvdis.gov.tw/"]:
        assert adjudicate(PageContext(url=url), [layer]).display_level == "banner"


async def test_llm_can_represent_non_otp_social_engineering():
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(
                    status="completed",
                    output_text=json.dumps(
                        {"finding": "suspicious", "confidence": 0.95, "reason_code": "scareware_pressure"}
                    ),
                )
            )
        ),
        close=AsyncMock(),
    )
    model = LLM(Settings(api_key="test", llm_enabled=True, allow_content_upload=True), client)
    ctx = PageContext(url="https://example.com", text="您的裝置遭病毒感染，立即聯絡客服。")
    result = await model.supplement(LayerResult(layer="L3"), ctx)
    assert result.verdict == "suspicious"
    assert "不是系統掃毒結果" in result.signals[0].detail
    assert adjudicate(ctx, [result]).display_level == "banner"
    assert "Win+R" in client.responses.create.call_args.kwargs["instructions"]


@pytest.mark.parametrize(
    "title,text,expected",
    [
        ("Example: AI-powered trading platform", "98% Reliability 10x Growth potential", True),
        ("Example: KI-gestützte Handelsplattform", "98% Verlässlichkeit 10x Wachstumspotenzial", True),
        ("Example 人工智能交易平台", "98% 可靠性 10倍 增长潜力", True),
        ("Analytics software", "98% Reliability 10x Growth potential", False),
        ("News report", "This trading platform claims 98% Reliability 10x Growth potential", False),
        ("Trading platform", "We explain risks and do not promise profits.", False),
    ],
)
def test_trading_promotion_requires_title_and_combination(title, text, expected):
    result = verify_l3(PageContext(url="https://example.com", title=title, text=text))
    assert any(s.id == "unsubstantiated_trading_claims" for s in result.signals) == expected
