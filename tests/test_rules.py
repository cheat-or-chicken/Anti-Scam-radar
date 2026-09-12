import pytest

from script.domains import same_site, trusted
from script.extract import extract_page
from script.layers import REGISTRY
from script.layers.adjudication import adjudicate, should_interrupt
from script.layers.rules import verify_l2, verify_l3, verify_l4, verify_l6, verify_l12, verify_l13
from script.models import Download, LayerResult, NetworkEvent, PageContext


@pytest.mark.parametrize("layer", list(REGISTRY))
def test_every_layer_has_valid_entrypoint(layer):
    r = REGISTRY[layer](PageContext(url="https://example.com"))
    assert isinstance(r, LayerResult)
    assert r.layer == layer
    assert 0 <= r.score <= 100


@pytest.mark.parametrize(
    "url", ["https://mvdis.gov.tw.evil.example", "https://evil-mvdis.gov.tw", "http://mvdis.gov.tw"]
)
def test_government_suffix_spoofs_not_trusted(url):
    assert not trusted(url)


def test_private_suffix_separates_tenants():
    assert not same_site("https://evil.pages.dev", "https://good.pages.dev")
    assert not same_site("https://a.vercel.app", "https://b.vercel.app")
    assert same_site("https://www.mvdis.gov.tw", "https://mvdis.gov.tw")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:pass@example.com",
        "https://example.com:8080",
        "https://exa\\mple.com",
        "https://example.com\n",
    ],
)
def test_invalid_url_rejected(url):
    with pytest.raises(ValueError):
        PageContext(url=url)


def test_official_otp_is_not_a_hard_rule():
    ctx = PageContext(
        url="https://www.mvdis.gov.tw", title="監理服務網", text="請輸入 OTP 登入", sensitive_fields=["otp"]
    )
    d = adjudicate(ctx, [verify_l2(ctx), verify_l3(ctx)])
    assert d.risk_score == 0
    assert not should_interrupt("password_field_focus", d)


def test_warning_article_not_social_engineering():
    ctx = PageContext(url="https://news.example", text="請勿安裝 AnyDesk。不要提供驗證碼給客服。")
    assert not verify_l3(ctx).signals
    assert not verify_l2(ctx).signals


def test_static_code_and_third_party_forms_not_observed_exfiltration():
    ctx = PageContext(
        url="https://shop.example", scripts=["eval(code)"], form_actions=["https://payments.example/pay"]
    )
    r = verify_l4(ctx)
    assert all(s.grade == "inferred" and not s.hard for s in r.signals)
    assert adjudicate(ctx, [r]).display_level != "block"


def test_confirmed_leak_blocks_but_untrusted_trace_does_not():
    ctx = PageContext(
        url="https://phish.example",
        network_trace=[NetworkEvent(url="https://leak.example", trigger="keyup", sensitive_data=True)] * 3,
    )
    assert not verify_l4(ctx).signals
    for e in ctx.network_trace:
        e.observed = True
    assert adjudicate(ctx, [verify_l4(ctx)]).display_level == "block"


def test_approved_payment_provider_is_not_leak():
    ctx = PageContext(
        url="https://shop.example",
        network_trace=[
            NetworkEvent(
                url="https://payments.example",
                observed=True,
                sensitive_data=True,
                authorized_destination=True,
            )
        ],
    )
    assert not verify_l4(ctx).signals


def test_canary_requires_actual_external_observation():
    ctx = PageContext(
        url="https://shop.example",
        network_trace=[NetworkEvent(url="https://shop.example/check", observed=True, canary_detected=True)],
    )
    assert not verify_l4(ctx).signals
    ctx.network_trace[0].url = "https://leak.example"
    assert verify_l4(ctx).signals[0].hard


def test_cloaking_difference_not_proof():
    ctx = PageContext(url="https://shop.example", probe_texts=["desktop home", "手機驗證碼登入頁面"])
    r = verify_l6(ctx)
    assert r.verdict == "suspicious"
    assert adjudicate(ctx, [r]).display_level != "block"


def test_download_and_qr():
    ctx = PageContext(
        url="https://example.com",
        downloads=[
            Download(
                filename="罰單.pdf.exe",
                url="https://example.com/file",
                declared_type="application/pdf",
                magic_hex="4d5a",
            )
        ],
        qr_payloads=["https://mvdis.gov.tw.evil.example", "javascript:alert(1)"],
    )
    assert {s.id for s in verify_l12(ctx).signals} >= {"disguised_download", "download_type_mismatch"}
    assert "qr_official_domain_embedded" in {s.id for s in verify_l13(ctx).signals}


def test_extract_does_not_capture_input_values():
    ctx = extract_page(
        "https://example.com",
        '<title>Test</title><input type="password" value="SECRET"><form action="/submit"></form><script>const x=1</script>',
    )
    assert "SECRET" not in ctx.model_dump_json()
    assert ctx.sensitive_fields
    assert ctx.form_actions == ["https://example.com/submit"]
