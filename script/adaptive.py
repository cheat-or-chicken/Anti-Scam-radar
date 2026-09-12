"""Declarative rule synthesis; generated code is never eval'd or imported."""

from typing import Literal

from pydantic import Field

from script.layers.rules import sig
from script.models import Model, PageContext


class Detector(Model):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    feature: Literal["external_sensitive_events", "sensitive_field_count", "redirect_count"]
    minimum: int = Field(ge=1, le=100)
    weight: int = Field(ge=1, le=20)
    provenance: str = Field(min_length=1, max_length=200)
    state: Literal["shadow", "active", "disabled"] = "shadow"


def detect(rule: Detector, ctx: PageContext, *, shadow: bool = False):
    if rule.state == "disabled" or (rule.state != "active" and not shadow):
        return None
    from script.domains import same_site

    features = {
        "external_sensitive_events": sum(
            e.observed and e.sensitive_data and not e.authorized_destination and not same_site(e.url, ctx.url)
            for e in ctx.network_trace
        ),
        "sensitive_field_count": len(ctx.sensitive_fields),
        "redirect_count": len(ctx.redirects),
    }
    if features[rule.feature] >= rule.minimum:
        return sig("adaptive_" + rule.id, "經人工核准的額外規則命中，需其他證據佐證", rule.weight)
    return None


async def synthesize(llm, summaries: list[dict]) -> Detector:
    # Accept only numeric/enumerated summaries, not sample URLs or page-controlled strings.
    safe = [
        {
            "external_sensitive_events": int(s.get("external_sensitive_events", 0)),
            "sensitive_field_count": int(s.get("sensitive_field_count", 0)),
            "redirect_count": int(s.get("redirect_count", 0)),
        }
        for s in summaries[:30]
    ]
    import json

    response = await llm.request(
        model=llm.settings.code_model,
        reasoning={"effort": "high"},
        instructions="提出一條額外可疑偵測規則；只能使用指定 DSL，state 必須 shadow。不能降低風險或改硬規則。",
        input=json.dumps(safe),
        text={
            "format": {
                "type": "json_schema",
                "name": "detector",
                "strict": True,
                "schema": {**Detector.model_json_schema(), "required": list(Detector.model_fields)},
            }
        },
    )
    if response.status != "completed":
        raise ValueError("incomplete_response")
    return Detector.model_validate_json(response.output_text).model_copy(update={"state": "shadow"})


def evaluate(rule: Detector, cases: list[tuple[PageContext, bool]]) -> dict:
    positives = sum(label for _, label in cases)
    negatives = len(cases) - positives
    fp = sum(bool(detect(rule, ctx, shadow=True)) and not label for ctx, label in cases)
    tp = sum(bool(detect(rule, ctx, shadow=True)) and label for ctx, label in cases)
    return {
        "count": len(cases),
        "positives": positives,
        "negatives": negatives,
        "tp": tp,
        "fp": fp,
        "fpr": fp / negatives if negatives else None,
        "recall": tp / positives if positives else None,
    }


def promote(rule: Detector, cases: list[tuple[PageContext, bool]], *, reviewed: bool = False) -> Detector:
    metrics = evaluate(rule, cases)  # Recompute, never trust model-provided performance numbers.
    if (
        not reviewed
        or metrics["negatives"] < 15
        or metrics["positives"] < 15
        or metrics["fpr"] != 0
        or metrics["recall"] < 0.5
    ):
        raise ValueError("requires human review, 15+15 labeled cases, zero false positives, recall >= 0.5")
    return rule.model_copy(update={"state": "active"})
