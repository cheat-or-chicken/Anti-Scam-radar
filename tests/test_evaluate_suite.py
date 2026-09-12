from ChatRoom.evaluate_suite import boundaries


def test_credential_disclosure_does_not_need_payment_event():
    assert boundaries({"first_harm_completed_turn": 8}) == (None, 8)


def test_exposure_is_earlier_than_payment():
    assert boundaries({"first_sensitive_banking_exposure_turn": 18, "first_payment_completed_turn": 26}) == (
        26,
        18,
    )


def test_legacy_payment_label_remains_supported():
    assert boundaries({"first_L3_turn": 21}) == (21, 21)
