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
    values.setdefault("resolution", dict(kind="none", evidence_turns=[], explanation=""))
    values.setdefault(
        "observation",
        dict(actor="counterparty", action_type="payment_request", object="驗證款", is_new_request=True),
    )
    if values["rule_ids"] and "rule_checks" not in kwargs:
        from ChatRoom.detector import KNOWLEDGE

        rules = {r["id"]: r for r in json.loads(KNOWLEDGE.read_text())["decision_rules"]}
        values["rule_checks"] = [
            dict(
                rule_id=r,
                normal_explanation_insufficient="用途與要求不符",
                conditions=[
                    dict(
                        requirement_index=i,
                        support="explicit",
                        evidence_turns=[e.turn for e in values["evidence"]],
                        explanation="測試證據",
                    )
                    for i, c in enumerate(rules[r]["required_evidence"], 1)
                ],
            )
            for r in values["rule_ids"]
        ]
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
        self.last_response = response.model_copy(deep=True)
        return response, "test-response", None

    def match_prediction(self, prediction, messages):
        current = messages[-1]
        decision = self.last_response
        observation = decision.observation
        match = next((m for m in decision.prediction_matches if m.prediction_id == prediction["id"]), None)
        valid = (
            match
            and match.evidence
            and all(e.turn == current["turn"] for e in match.evidence)
            and observation
            and observation.actor == current["sender"] != "user"
            and observation.actor == prediction["actor"]
            and observation.action_type == prediction["action_type"]
            and observation.is_new_request
        )
        return dict(
            outcome="matched" if valid else "not_matched",
            matched_turn=current["turn"] if valid else None,
            evidence=[e.model_dump() for e in match.evidence] if valid else [],
            reason="stub",
        )


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
            answer(
                prediction=Prediction(
                    actor="counterparty",
                    action_type="payment_request",
                    object="驗證款",
                    action="要求付款",
                    within_next_messages=2,
                )
            ),
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
    initial = answer(
        prediction=Prediction(
            actor="counterparty",
            action_type="payment_request",
            object="驗證款",
            action="要求付款",
            within_next_messages=2,
        )
    )
    invalid = answer(
        prediction_matches=[Match(prediction_id="p1", evidence=[Evidence(turn=1, quote="你好")])]
    )
    detector = StubDetector(tmp_path, [initial, invalid, invalid])
    sid = detector.create_session()
    detector.analyze(sid, {"turn": 1, "text": "你好"})
    result = detector.analyze(sid, {"turn": 2, "text": "第二則"})
    assert result["status"] == "ok"
    assert result["prediction_verifications"][0]["outcome"] == "not_matched"
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


def test_unresolved_warning_survives_reassurance_and_can_be_corrected(tmp_path):
    warning = answer(
        status="warn", rule_ids=["R_PAYMENT_PURPOSE"], evidence=[Evidence(turn=1, quote="驗證要轉帳")]
    )
    correction = answer(
        resolution=dict(
            kind="corrected_interpretation", evidence_turns=[1], explanation="原文被誤讀；撤回付款目的判斷"
        )
    )
    detector = StubDetector(tmp_path, [warning, answer(), correction])
    sid = detector.create_session()
    detector.analyze(sid, {"turn": 1, "text": "驗證要轉帳"})
    retained = detector.analyze(sid, {"turn": 2, "text": "放心，正在處理"})
    assert retained["decision"]["status"] == "warn" and retained["risk_retained"]
    corrected = detector.analyze(sid, {"turn": 3, "text": "重新檢視原文"})
    assert corrected["decision"]["status"] == "monitor"
    assert corrected["first_alert_turn"] == 1


@pytest.mark.parametrize(
    "sender,action_type,new_request",
    [
        ("user", "payment_request", True),
        ("counterparty", "other", True),
        ("counterparty", "payment_request", False),
    ],
)
def test_prediction_rejects_wrong_actor_action_or_old_request(tmp_path, sender, action_type, new_request):
    initial = answer(
        prediction=Prediction(
            actor="counterparty",
            action_type="payment_request",
            object="驗證款",
            action="要求驗證款",
            within_next_messages=2,
        )
    )
    match = answer(
        observation=dict(actor=sender, action_type=action_type, object="驗證款", is_new_request=new_request),
        prediction_matches=[Match(prediction_id="p1", evidence=[Evidence(turn=2, quote="已付款")])],
    )
    detector = StubDetector(tmp_path, [initial, match])
    sid = detector.create_session()
    detector.analyze(sid, {"turn": 1, "text": "需要處理帳戶"})
    result = detector.analyze(sid, {"turn": 2, "sender": sender, "text": "已付款"})
    assert result["predictions"][0]["status"] == "pending"
    assert result["prediction_verifications"][0]["outcome"] == "not_matched"


def test_rule_missing_required_conditions_is_not_a_valid_warning(tmp_path):
    invalid = answer(
        status="warn",
        rule_ids=["R_SENSITIVE_ACCESS"],
        evidence=[Evidence(turn=1, quote="分享一般畫面")],
        rule_checks=[],
    )
    detector = StubDetector(tmp_path, [invalid, invalid])
    result = detector.analyze(detector.create_session(), {"turn": 1, "text": "分享一般畫面"})
    assert result["status"] == "analysis_error"


def test_unknown_required_condition_cannot_support_warning(tmp_path):
    candidate = answer(
        status="warn", rule_ids=["R_SENSITIVE_ACCESS"], evidence=[Evidence(turn=1, quote="請分享畫面")]
    )
    candidate.rule_checks[0].conditions[1].support = "unknown"
    detector = StubDetector(tmp_path, [candidate])
    result = detector.analyze(detector.create_session(), {"turn": 1, "text": "請分享畫面"})
    assert result["status"] == "ok"
    assert result["decision"]["status"] == "monitor"
    assert result["rejected_rules"] == ["R_SENSITIVE_ACCESS"]
    assert result["first_alert_turn"] is None


def test_condition_sources_are_resolved_even_if_top_level_omits_them(tmp_path):
    candidate = answer(
        status="warn", rule_ids=["R_PAYMENT_PURPOSE"], evidence=[Evidence(turn=2, quote="請轉帳")]
    )
    candidate.rule_checks[0].conditions[0].evidence_turns = [1]
    detector = StubDetector(tmp_path, [answer(), candidate])
    sid = detector.create_session()
    detector.analyze(sid, {"turn": 1, "text": "解除異常需要驗證"})
    result = detector.analyze(sid, {"turn": 2, "text": "請轉帳"})
    assert result["decision"]["status"] == "warn"
    assert {e["turn"] for e in result["decision"]["evidence"]} == {1, 2}


def test_incomplete_new_rule_does_not_erase_existing_supported_warning(tmp_path):
    first = answer(
        status="warn", rule_ids=["R_PAYMENT_PURPOSE"], evidence=[Evidence(turn=1, quote="驗證要轉帳")]
    )
    malformed = answer(
        status="warn",
        rule_ids=["R_SENSITIVE_ACCESS"],
        evidence=[Evidence(turn=2, quote="下一步")],
        rule_checks=[],
    )
    detector = StubDetector(tmp_path, [first, malformed])
    sid = detector.create_session()
    detector.analyze(sid, {"turn": 1, "text": "驗證要轉帳"})
    result = detector.analyze(sid, {"turn": 2, "text": "下一步"})
    assert result["status"] == "ok"
    assert result["decision"]["rule_ids"] == ["R_PAYMENT_PURPOSE"]
    assert result["risk_retained"]
    assert result["rejected_rules"] == ["R_SENSITIVE_ACCESS"]


def test_prize_card_request_warns_before_submission_even_if_model_misses(tmp_path):
    from ChatRoom.detector import ROOT

    messages = json.loads((ROOT / "data/reconstructed/B5_假中獎信用卡驗證盜刷.replay.json").read_text())[
        "messages"
    ]
    detector = StubDetector(tmp_path, [answer() for _ in messages[:8]])
    sid = detector.create_session()
    for message in messages[:8]:
        result = detector.analyze(sid, message)
        if message["turn"] < 5:
            assert result["first_alert_turn"] is None
        else:
            assert result["first_alert_turn"] == 5
            assert result["decision"]["status"] == "warn"
        if message["turn"] == 5:
            assert result["request_guard"]
            assert "先不要" in result["decision"]["recommended_action"]
            assert max(e["turn"] for e in result["decision"]["evidence"]) == 5
    assert result["intervention"] == {"phase": "reported_submitted", "reported_turn": 8}
    assert "你表示已送出" in result["decision"]["recommended_action"]
    assert len(detector.payloads[4]["messages"]) == 5


@pytest.mark.parametrize(
    "text",
    [
        "請填信用卡卡號、有效期限與安全碼以支付本次購物款項。",
        "領獎不需要信用卡卡號與安全碼，請勿提供。",
        "請填寫姓名即可領獎，不需卡號與安全碼。",
        "詐騙範例：「請填卡號與安全碼以領獎」。",
    ],
)
def test_request_guard_does_not_flag_checkout_or_education(tmp_path, text):
    detector = StubDetector(tmp_path, [answer()])
    result = detector.analyze(detector.create_session(), {"turn": 1, "sender": "page", "text": text})
    assert result["decision"]["status"] == "monitor"
    assert not result["request_guard"]


@pytest.mark.parametrize("text", ["卡號還沒有送出", "如果信用卡已送出怎麼辦？", "卡號填好了，但還沒送出。"])
def test_submission_wording_requires_actual_user_report(text):
    from ChatRoom.intervention import reported_card_submission

    assert reported_card_submission([{"sender": "user", "turn": 1, "text": text}]) is None
