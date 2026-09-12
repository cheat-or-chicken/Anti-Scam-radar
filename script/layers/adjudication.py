from script.domains import trusted
from script.models import Decision, LayerResult, PageContext, result

HARD_SIGNALS = {"keystroke_exfil", "sensitive_external_transfer", "canary_exfil"}
TRIGGERS = ["password_field_focus", "sensitive_field_focus", "submit", "download_start"]


def adjudicate(ctx: PageContext, layers: list[LayerResult]) -> Decision:
    # Signal IDs deduplicate evidence. A model can never manufacture an observed hard finding.
    unique = {}
    for layer in layers:
        for signal in layer.signals:
            unique.setdefault(signal.id, (layer.layer, signal))
    items = list(unique.values())
    hard = any(
        layer == "L4" and s.id in HARD_SIGNALS and s.hard and s.grade == "observed" for layer, s in items
    )
    hard = hard or any(layer == "BLOCKLIST" and s.id == "listed_domain" and s.hard for layer, s in items)
    evidence_layers = {
        layer for layer, s in items if s.weight >= 15 and layer not in {"L10", "L16", "ADAPTIVE"}
    }
    score = min(100, sum(s.weight for _, s in items))
    if not hard and len(evidence_layers) < 2:
        score = min(score, 55)
    if hard:
        score = 100
    is_trusted = trusted(ctx.url)
    display = "block" if hard or score >= 80 else "banner" if score > 0 else "icon"
    if ctx.behavior == "social_link" and score > 0 and display == "icon":
        display = "banner"
    if is_trusted:
        display = "banner" if score > 0 else "icon"  # Trusted sites still show warnings.
    triggers = TRIGGERS.copy() if score >= 15 and not is_trusted else []
    ordered = sorted(items, key=lambda pair: pair[1].weight, reverse=True)
    category = "品牌或機構冒用疑慮" if any(s.id == "brand_domain_mismatch" for _, s in items) else "未分類"
    if any(layer == "L3" for layer, _ in items):
        category = "話術詐騙疑慮"
    return Decision(
        risk_score=score,
        category=category,
        display_level=display,
        interrupt_triggers=triggers,
        reasons=[s.detail for _, s in ordered],
        trusted_domain=is_trusted,
    )


def should_interrupt(behavior: str, decision: Decision) -> bool:
    return not decision.trusted_domain and (
        decision.display_level == "block" or behavior in decision.interrupt_triggers
    )


def verify_l17(ctx: PageContext, layers: list[LayerResult]) -> LayerResult:
    decision = adjudicate(ctx, layers)
    return result("L17", []).model_copy(
        update={
            "score": decision.risk_score,
            "verdict": "suspicious" if decision.risk_score else "unknown",
            "user_facing_reason": "；".join(decision.reasons) or "未發現規則命中；資料覆蓋有限，不能宣告安全",
        }
    )
