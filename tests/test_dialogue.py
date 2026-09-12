import json

import pytest

from ChatRoom.detector import Decision, Detector, Evidence, Match, Prediction, normalize_message


def answer(**kwargs):
    values = dict(
        status="monitor",
        reason="尚待確認",
        normal_explanation="可能是正常交易",
        recommended_action="",
        stages=["S0"],
        rule_ids=[],
        evidence=[],
        prediction=None,
        prediction_matches=[],
    )
    values.update(kwargs)
    return Decision(**values)


class StubDetector(Detector):
    def __init__(self, tmp_path, responses):
        super().__init__(log_dir=tmp_path)
        self.responses = iter(responses)
        self.payloads = []

    def call(self, payload):
        self.payloads.append(json.loads(json.dumps(payload)))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response, "test-response", None


def test_allowlist_drops_case_and_outcome():
    raw = {
        "text": "你好",
        "sender": "user",
        "channel": "line",
        "case_id": "B1_scam",
        "first_L3_turn": 21,
        "attachments": [{"caption": "照片", "simulation_only": True}],
    }
    message = normalize_message(raw, 1)
    assert set(message) == {"turn", "sender", "channel", "text", "attachment_captions"}
    assert "simulation_only" not in json.dumps(message)


def test_prefix_only_idempotence_and_conflict(tmp_path):
    detector = StubDetector(tmp_path, [answer(), answer()])
    sid = detector.create_session()
    first = detector.analyze(sid, {"turn": 1, "text": "你好"})
    assert detector.analyze(sid, {"turn": 1, "text": "你好"}) == first
    with pytest.raises(ValueError):
        detector.analyze(sid, {"turn": 1, "text": "不同"})
    with pytest.raises(ValueError):
        detector.analyze(sid, {"turn": 3, "text": "跳輪"})
    detector.analyze(sid, {"turn": 2, "text": "第二則"})
    assert [len(p["messages"]) for p in detector.payloads] == [1, 2]
    assert "第二則" not in json.dumps(detector.payloads[0], ensure_ascii=False)


def test_bad_evidence_never_becomes_warning(tmp_path):
    invalid = answer(status="warn", rule_ids=["R_PAYMENT_PURPOSE"], evidence=[Evidence(turn=2, quote="未來")])
    detector = StubDetector(tmp_path, [invalid, invalid])
    result = detector.analyze(detector.create_session(), {"turn": 1, "text": "你好"})
    assert result["status"] == "analysis_error"
    assert result["decision"] is None
    assert result["first_alert_turn"] is None


def test_api_error_not_safe_and_does_not_expose_secret(tmp_path):
    detector = StubDetector(tmp_path, [RuntimeError("secret-credential")])
    result = detector.analyze(detector.create_session(), {"turn": 1, "text": "你好"})
    assert result["status"] == "analysis_error"
    assert "secret-credential" not in json.dumps(result)
    assert "secret-credential" not in next(tmp_path.glob("*.jsonl")).read_text()


def test_prediction_only_matches_later_message_and_first_alert_persists(tmp_path):
    detector = StubDetector(
        tmp_path,
        [
            answer(prediction=Prediction(action="要求付款", within_next_messages=2)),
            answer(
                status="warn",
                rule_ids=["R_PAYMENT_PURPOSE"],
                evidence=[Evidence(turn=2, quote="驗證要轉帳")],
                prediction_matches=[
                    Match(prediction_id="p1", evidence=[Evidence(turn=2, quote="驗證要轉帳")])
                ],
            ),
            answer(),
        ],
    )
    sid = detector.create_session()
    detector.analyze(sid, {"turn": 1, "text": "帳戶異常"})
    second = detector.analyze(sid, {"turn": 2, "text": "驗證要轉帳"})
    assert second["predictions"][0]["status"] == "matched"
    third = detector.analyze(sid, {"turn": 3, "text": "我不轉了"})
    assert third["first_alert_turn"] == 2


def test_prediction_cannot_use_old_quote(tmp_path):
    initial = answer(prediction=Prediction(action="要求付款", within_next_messages=2))
    invalid = answer(
        prediction_matches=[Match(prediction_id="p1", evidence=[Evidence(turn=1, quote="你好")])]
    )
    detector = StubDetector(tmp_path, [initial, invalid, invalid])
    sid = detector.create_session()
    detector.analyze(sid, {"turn": 1, "text": "你好"})
    result = detector.analyze(sid, {"turn": 2, "text": "第二則"})
    assert result["status"] == "ok"
    assert result["rejected_prediction_matches"]
    assert result["decision"]["prediction_matches"] == []
    assert result["predictions"][0]["status"] == "pending"


def test_normal_payment_has_no_programmatic_forced_alert(tmp_path):
    detector = StubDetector(tmp_path, [answer(status="insufficient")])
    result = detector.analyze(detector.create_session(), {"turn": 1, "text": "商品貨款轉帳完成"})
    assert result["first_alert_turn"] is None
    # This verifies plumbing only; not a claim about actual model classification.


def test_local_key_overrides_inherited_without_loading_unrelated_vars(tmp_path, monkeypatch):
    from ChatRoom.detector import load_local_env

    monkeypatch.setenv("OPENAI_API_KEY", "old-test-value")
    monkeypatch.delenv("UNRELATED_SETTING", raising=False)
    path = tmp_path / ".env.local"
    path.write_text("OPENAI_API_KEY=new-test-value\nUNRELATED_SETTING=ignored\n")
    load_local_env(path)
    import os

    assert os.environ["OPENAI_API_KEY"] == "new-test-value"
    assert "UNRELATED_SETTING" not in os.environ


def test_citations_resolved_from_source_not_generated_text():
    from ChatRoom.detector import ModelDecision, resolve_citations

    raw = answer().model_dump(exclude={"evidence", "prediction_matches"})
    raw.update(evidence_turns=[1, 1], prediction_matches=[])
    model = ModelDecision.model_validate(raw)
    source = normalize_message({"text": "您好，您目前停在哪個畫面？"}, 1)
    decision = resolve_citations(model, [source])
    assert decision.evidence == [Evidence(turn=1, quote=source["text"])]
    model.evidence_turns = [2]
    with pytest.raises(ValueError):
        resolve_citations(model, [source])


def test_latest_failed_turn_can_retry_without_incrementing(tmp_path):
    detector = StubDetector(tmp_path, [RuntimeError("temporary"), answer()])
    sid = detector.create_session()
    raw = {"turn": 1, "text": "你好"}
    assert detector.analyze(sid, raw)["status"] == "analysis_error"
    retried = detector.analyze(sid, raw)
    assert retried["status"] == "ok" and retried["turn"] == 1
    assert len(detector.sessions[sid]["messages"]) == 1
    assert detector.analyze(sid, raw) == retried
    assert len(detector.payloads) == 2
