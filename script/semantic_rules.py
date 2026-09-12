"""Shared conservative combinations for common social-engineering text."""

import json
import re
from pathlib import Path

DATA = Path(__file__).parent / "data"
MESSAGES = json.loads((DATA / "risk_messages.json").read_text())
RULES = json.loads((DATA / "semantic_rules.json").read_text())

SEMANTIC_GUIDANCE = (
    "跨語言檢查：自稱交易平台、搭配數倍成長與高可靠性數字但未附可核對證據時，可用 unsubstantiated_trading_claims 表示需查證的宣傳，不能把成長潛力說成保證收益。一般企業願景、真實引用報告或教學討論不能單憑數字判詐騙。"
    "先辨識頁面要求使用者做什麼，再判斷是否以恐嚇、保證收益、獎金或帳戶異常促使危險操作。"
    "涵蓋假中毒並催促安裝或撥號、假真人驗證要求 Win+R 或貼上指令、先付費才能提領或領獎、"
    "遠端控制與投資承諾。不是只有 OTP 才算可疑。新聞引述、防詐教育、正常登入與合理客服要區分。"
    "僅依提供文字，不从亂碼網址、TLD、CDN 或使用者聲稱推定詐騙。缺內容或 404 應回 unknown。"
)


def semantic_signals(text, title=""):
    combined = title + "\n" + text
    found = {}
    for sentence in re.split(r"[。！？\n.!?]", text):
        if re.search(r"不要|切勿|請勿|不會|勿將|防詐|詐騙案例|do not|never|beware", sentence, re.I):
            continue
        for rule in RULES:
            if rule.get("scope") == "page":
                continue
            if all(re.search(pattern, sentence, re.I) for pattern in rule["patterns"]):
                found[rule["id"]] = {**rule, "detail": MESSAGES[rule["id"]]}
    for rule in RULES:
        if (
            rule.get("scope") == "page"
            and re.search(rule["patterns"][0], title, re.I)
            and all(re.search(pattern, combined, re.I | re.S) for pattern in rule["patterns"])
        ):
            found[rule["id"]] = {**rule, "detail": MESSAGES[rule["id"]]}
    return [{"id": r["id"], "detail": r["detail"], "weight": r["weight"]} for r in found.values()]
