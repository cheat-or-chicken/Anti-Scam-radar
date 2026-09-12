import json
from pathlib import Path

import pytest

from script.config import Settings
from script.layers import REGISTRY
from script.models import PageContext
from script.pipeline import analyze
from script.storage import Store, fingerprint


@pytest.mark.parametrize(
    "file,blocked",
    [
        ("government-phishing.json", True),
        ("official-login.json", False),
        ("observed-exfiltration.json", True),
    ],
)
async def test_demo_fixtures(tmp_path, file, blocked):
    ctx = PageContext.model_validate_json((Path("fixtures") / file).read_text())
    settings = Settings(database_path=str(tmp_path / "audit.db"))
    r = await analyze(ctx, settings)
    assert r.interrupted is blocked
    assert r.llm_calls == 0
    assert len(r.layers) == 19
    assert r.audit_id
    saved = Store(settings.database_path).replay(r.audit_id)
    assert "token=" not in json.dumps(saved)
    assert "DEMO_ONLY" not in json.dumps(saved)


async def test_failure_isolated(monkeypatch):
    def fail(ctx):
        raise RuntimeError("SECRET")

    monkeypatch.setitem(REGISTRY, "L4", fail)
    r = await analyze(PageContext(url="https://example.com"), Settings(audit_enabled=False))
    assert r.layers[4].status == "error"
    assert r.layers[1].status == "ok"
    assert "SECRET" not in r.model_dump_json()


async def test_missing_key_does_not_disable_rules():
    ctx = PageContext(url="https://fake.example", title="監理服務網", domain_age_days=2)
    r = await analyze(ctx, Settings(audit_enabled=False, llm_enabled=True, allow_content_upload=True))
    assert r.llm_calls == 0
    assert r.decision.risk_score >= 60


def test_reports_consent_dedup_and_separate_review(tmp_path):
    s = Store(str(tmp_path / "db.sqlite"))
    url = "https://a.pages.dev"
    with pytest.raises(ValueError):
        s.report(url, "template", fingerprint("one"), consent=False)
    for _ in range(2):
        s.report(url, "template", fingerprint("one"), consent=True)
    assert s.report_count(url) == 1
    assert s.report_count("https://b.pages.dev") == 0
    assert not s.query_fingerprint_db("template")["matched"]
    s.add_reviewed_fingerprint("template", "manual-review-1")
    assert s.query_fingerprint_db("template")["matched"]


async def test_community_alone_never_blocks(tmp_path):
    settings = Settings(database_path=str(tmp_path / "db.sqlite"))
    store = Store(settings.database_path)
    for i in range(30):
        store.report("https://example.com", "template", fingerprint(str(i)), consent=True)
    r = await analyze(PageContext(url="https://example.com"), settings)
    assert r.decision.display_level != "block"


async def test_audit_failure_still_returns_verdict(monkeypatch, tmp_path):
    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Store, "record", fail)
    r = await analyze(
        PageContext(url="https://fake.example", title="監理服務網"),
        Settings(database_path=str(tmp_path / "db.sqlite")),
    )
    assert r.audit_status == "error"
    assert r.audit_id is None
    assert r.decision.risk_score == 40


def test_adjudication_lists_all_problems():
    from script.layers.adjudication import adjudicate
    from script.models import Signal, result

    signals = [Signal(id=f"risk_{i}", detail=f"Problem {i}", weight=5) for i in range(6)]
    decision = adjudicate(PageContext(url="https://example.com"), [result("L3", signals)])
    assert len(decision.reasons) == 6
    assert set(decision.reasons) == {s.detail for s in signals}
