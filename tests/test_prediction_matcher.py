import json
from types import SimpleNamespace

import pytest

from ChatRoom.prediction_matcher import PredictionMatcher, final_status


def pred():
    return dict(
        actor="support",
        action_type="sensitive_access_request",
        object="OTP",
        action="要求簡訊認證碼",
        created_turn=1,
        expires_turn=3,
    )


def messages():
    return [
        dict(turn=1, sender="support", text="稍後核對"),
        dict(turn=2, sender="user", text="好了"),
        dict(turn=3, sender="support", text="請輸入簡訊代碼"),
        dict(turn=4, sender="support", text="不應看見的未來"),
    ]


def checker(audit_overrides=None, **overrides):
    value = dict(
        outcome="matched",
        matched_turn=3,
        semantic_correspondence=True,
        new_after_prediction=True,
        reason="OTP與簡訊代碼相符",
    )
    value.update(overrides)
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if kwargs["text"]["format"]["name"] == "prediction_audit":
            audit = dict(
                outcome="matched",
                required_action="要求OTP",
                observed_action="要求簡訊代碼",
                prior_equivalent_turns=[],
                reason="新要求吻合",
            )
            audit.update(audit_overrides or {})
            return SimpleNamespace(
                status="completed", output_text=json.dumps(audit), id="audit-id", usage=None
            )
        return SimpleNamespace(status="completed", output_text=json.dumps(value), id="test-id", usage=None)

    return PredictionMatcher("test", SimpleNamespace(responses=SimpleNamespace(create=create))), calls


def test_semantic_match_uses_source_and_excludes_future():
    matcher, calls = checker()
    result = matcher.check(pred(), messages())
    assert result["outcome"] == "matched"
    assert result["evidence"] == [{"turn": 3, "quote": "請輸入簡訊代碼"}]
    assert len(json.loads(calls[0]["input"])["messages"]) == 3
    assert final_status(result, pred(), 4) == "matched"


@pytest.mark.parametrize(
    "overrides",
    [
        {"matched_turn": 2},
        {"matched_turn": 4},
        {"matched_turn": 1},
        {"new_after_prediction": False},
        {"semantic_correspondence": False},
    ],
)
def test_invalid_actor_window_or_newness_cannot_be_matched(overrides):
    matcher, _ = checker(**overrides)
    assert matcher.check(pred(), messages())["outcome"] == "error"


def test_no_counterparty_event_requires_no_api():
    matcher, calls = checker()
    result = matcher.check(pred(), messages()[:2])
    assert not calls
    assert final_status(result, pred(), 2) == "pending"


def test_uncertainty_is_not_counted_as_miss():
    matcher, _ = checker(outcome="uncertain", matched_turn=None)
    result = matcher.check(pred(), messages())
    assert final_status(result, pred(), 4) == "unverified"


def test_completed_window_without_match_is_missed():
    matcher, _ = checker(outcome="not_matched", matched_turn=None, new_after_prediction=False)
    result = matcher.check(pred(), messages())
    assert final_status(result, pred(), 4) == "missed"


def test_prior_existing_obligation_is_not_a_new_match():
    matcher, _ = checker(audit_overrides={"prior_equivalent_turns": [1], "reason": "同一要求的催促"})
    result = matcher.check(pred(), messages())
    assert result["outcome"] == "not_matched"
    assert result["evidence"] == []


def test_auditor_uncertainty_remains_unverified():
    matcher, _ = checker(audit_overrides={"outcome": "uncertain"})
    result = matcher.check(pred(), messages())
    assert final_status(result, pred(), 4) == "unverified"
