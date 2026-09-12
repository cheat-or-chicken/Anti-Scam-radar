"""Narrow request-time safeguard and source-grounded intervention wording."""

import re


def prize_card_request(message):
    """Only direct requests containing both prize context and card security data.

    Quoted/educational/negated statements remain for semantic analysis. This is a
    conservative supplement, not a general classifier for checkout pages.
    """
    text = message["text"].strip()
    return (
        message["sender"] != "user"
        and bool(re.match(r"^(?:請|麻煩)(?:填(?:寫)?|輸入|提供|提交)", text))
        and bool(re.search(r"領獎|中獎|獎金", text))
        and "卡號" in text
        and bool(re.search(r"安全碼|檢查碼|CVV|CVC", text, re.I))
        and not re.search(r'不要|不需|不必|無需|勿|切勿|例如|範例|詐騙|[「」“”"]', text)
    )


def reported_card_submission(messages):
    """A user report is not proof that an external payment/submission occurred."""
    for message in reversed(messages):
        text = message["text"]
        if (
            message["sender"] == "user"
            and re.search(r"卡號|信用卡|安全碼", text)
            and re.search(r"已(?:經)?(?:填好)?(?:送出|提交)|(?:填好)?送出了|提交了", text)
            and not re.search(r"還沒|尚未|沒有|未曾|如果|假如|不要|不會|沒送|未送|[？?「」]", text)
        ):
            return message["turn"]
    return None
