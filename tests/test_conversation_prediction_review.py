import json
from types import SimpleNamespace

from ChatRoom.conversation_prediction_review import ConversationReviewer


def setup(outputs):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            status="completed", output_text=json.dumps({"items": outputs.pop(0)}), id="test", usage=None
        )

    reviewer = ConversationReviewer("test", SimpleNamespace(responses=SimpleNamespace(create=create)))
    prediction = dict(
        id="p1",
        created_turn=1,
        actor="seller",
        action_type="payment_request",
        object="付款",
        action="繼續催促付款",
        expires_turn=2,
    )
    messages = [dict(turn=i, sender="seller" if i in (1, 5) else "user", text=str(i)) for i in range(1, 6)]
    return reviewer, prediction, messages, calls


def item(turn):
    return dict(prediction_id="p1", outcome="matched", matched_turn=turn, reason="後續催促")


def test_full_conversation_allows_after_old_expiry():
    reviewer, p, m, calls = setup([[item(5)]])
    result = reviewer.check([p], m)
    assert result["matched"] == 1
    payload = json.loads(calls[0]["input"])
    assert len(payload["messages"]) == 5
    assert "expires_turn" not in payload["predictions"][0]
    assert result["items"][0]["evidence"] == [{"turn": 5, "quote": "5"}]


def test_current_turn_is_rejected_and_feedback_can_repair():
    reviewer, p, m, calls = setup([[item(1)], [item(5)]])
    result = reviewer.check([p], m)
    assert result["matched"] == 1
    assert json.loads(calls[1]["input"])["validation_feedback"]


def test_persistent_wrong_actor_is_unconfirmed_not_false_match():
    reviewer, p, m, calls = setup([[item(2)], [item(2)]])
    result = reviewer.check([p], m)
    assert result["uncertain"] == 1 and result["matched"] == 0
    assert result["items"][0]["validation_error"]


def test_empty_predictions_does_not_call_model():
    reviewer, p, m, calls = setup([])
    assert reviewer.check([], m)["rate"] is None
    assert not calls
