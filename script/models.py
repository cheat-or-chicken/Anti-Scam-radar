from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Signal(Model):
    id: str
    detail: str
    grade: Literal["observed", "inferred"] = "inferred"
    weight: int = Field(default=15, ge=0, le=100)
    hard: bool = False


class LayerResult(Model):
    layer: str
    verdict: Literal["suspicious", "clean", "unknown"] = "unknown"
    score: int = Field(default=0, ge=0, le=100)
    confidence: float = Field(default=0, ge=0, le=1)
    evidence_grade: Literal["observed", "inferred"] = "inferred"
    signals: list[Signal] = Field(default_factory=list)
    user_facing_reason: str = "資料不足，無法判定"
    status: Literal["ok", "missing", "skipped", "error"] = "missing"
    feedback: list[str] = Field(default_factory=list)


class NetworkEvent(Model):
    url: str
    trigger: str = "unknown"
    sensitive_data: bool = False
    canary_detected: bool = False
    authorized_destination: bool = False
    # Only a trusted collector may set observed=True; never derive this from JS text.
    observed: bool = False

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        from script.domains import parse_url

        parse_url(value)
        return value


class Download(Model):
    filename: str
    url: str
    declared_type: str = ""
    magic_hex: str = Field(default="", max_length=64)
    user_initiated: bool = True

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        from script.domains import parse_url

        parse_url(value)
        return value


class PageContext(Model):
    dom_collected: bool = False
    url: str = Field(max_length=8192)
    title: str = Field(default="", max_length=1000)
    text: str = Field(default="", max_length=50000)
    html: str = Field(default="", max_length=500000)
    scripts: list[str] = Field(default_factory=list, max_length=20)
    claimed_brand: str | None = None
    sensitive_fields: list[str] = Field(default_factory=list, max_length=100)
    redirects: list[str] = Field(default_factory=list, max_length=20)
    form_actions: list[str] = Field(default_factory=list, max_length=100)
    network_trace: list[NetworkEvent] = Field(default_factory=list, max_length=1000)
    trace_collected: bool = False
    domain_age_days: int | None = Field(default=None, ge=0)
    tls_valid: bool | None = None
    probe_texts: list[str] = Field(default_factory=list, max_length=5)
    previous_sensitive_fields: list[str] | None = None
    downloads: list[Download] = Field(default_factory=list, max_length=100)
    qr_payloads: list[str] = Field(default_factory=list, max_length=100)
    hidden_text: str = Field(default="", max_length=20000)
    delayed_sensitive_injection: bool = False
    missing_business_pages: bool | None = None
    behavior: Literal[
        "browse", "social_link", "password_field_focus", "sensitive_field_focus", "submit", "download_start"
    ] = "browse"

    @field_validator("url", "redirects", "form_actions")
    @classmethod
    def valid_urls(cls, value):
        from script.domains import parse_url

        for url in value if isinstance(value, list) else [value]:
            parse_url(url)
        return value

    @field_validator("scripts", "probe_texts", "qr_payloads")
    @classmethod
    def bounded_text(cls, values):
        if any(len(value) > 50000 for value in values):
            raise ValueError("text item exceeds 50000 characters")
        return values


class Decision(Model):
    risk_score: int = Field(ge=0, le=100)
    category: str = "未分類"
    display_level: Literal["icon", "banner", "block"]
    interrupt_triggers: list[str]
    reasons: list[str]
    trusted_domain: bool
    coverage: Literal["partial", "complete"] = "partial"


class Analysis(Model):
    schema_version: str = "1.0"
    gate: str
    layers: list[LayerResult]
    decision: Decision
    interrupted: bool
    investigation_trace: list[dict[str, str | int]] = Field(default_factory=list)
    llm_calls: int = 0
    audit_id: str | None = None
    audit_status: Literal["disabled", "saved", "error"] = "disabled"


def result(layer: str, signals: list[Signal], *, available: bool = True) -> LayerResult:
    if not available and not signals:
        return LayerResult(layer=layer)
    return LayerResult(
        layer=layer,
        verdict="suspicious" if signals else "clean",
        score=min(100, sum(s.weight for s in signals)),
        confidence=0.85 if signals else 0.6,
        evidence_grade="observed" if any(s.grade == "observed" for s in signals) else "inferred",
        signals=signals,
        user_facing_reason=signals[0].detail if signals else "已提供的資料未命中本層規則；不代表網站安全",
        status="ok",
    )
