"""Google Safe Browsing and Web Risk URL reputation lookups."""

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from typing import ClassVar
from urllib.parse import urlencode

from script.config import Settings
from script.models import LayerResult, PageContext, Signal
from script.network import SafeFetcher


class GoogleUrlReputation:
    """Look up only the page URL, without crawling or uploading page content."""

    _cache: ClassVar[dict[tuple[str, str], tuple[datetime, LayerResult]]] = {}

    def __init__(self, settings: Settings, fetcher: SafeFetcher | None = None):
        self.settings = settings
        self.fetcher = fetcher or SafeFetcher(settings)

    async def check(self, ctx: PageContext) -> LayerResult:
        provider = self.settings.google_url_reputation_provider
        if provider == "none":
            return self._skipped("Google URL 信譽查核未啟用")
        if not self.settings.network_enabled:
            return self._skipped("Google URL 信譽查核需要啟用網路查證")

        api_key = self.settings.google_url_reputation_api_key.get_secret_value()
        if not api_key:
            return self._skipped("Google URL 信譽查核需要 API key")

        cache_key = (provider, ctx.url)
        cached = self._cache.get(cache_key)
        if cached and cached[0] > datetime.now(UTC):
            return cached[1]

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(self.fetcher.get, self._endpoint(provider, ctx.url, api_key)),
                timeout=self.settings.timeout_seconds + 1,
            )
            data = json.loads(response["text"])
            if not isinstance(data, dict):
                raise ValueError("unexpected Google response")
            threat_types = self._threat_types(provider, data)
            response_result = self._result(provider, threat_types)
            self._cache[cache_key] = (self._expiry(provider, data), response_result)
            return response_result
        except Exception:
            # Never expose request URLs, API keys, or upstream body content in the analysis result.
            return LayerResult(
                layer="GOOGLE_URL_REPUTATION",
                status="error",
                user_facing_reason="Google URL 信譽查核暫時無法完成",
            )

    @staticmethod
    def _endpoint(provider: str, url: str, api_key: str) -> str:
        if provider == "safe_browsing":
            query = urlencode([("key", api_key), ("urls[]", url)])
            return f"https://safebrowsing.googleapis.com/v5/urls:search?{query}"
        query = urlencode(
            [
                ("key", api_key),
                ("uri", url),
                ("threatTypes", "MALWARE"),
                ("threatTypes", "SOCIAL_ENGINEERING"),
                ("threatTypes", "UNWANTED_SOFTWARE"),
            ]
        )
        return f"https://webrisk.googleapis.com/v1/uris:search?{query}"

    @staticmethod
    def _threat_types(provider: str, data: dict) -> list[str]:
        if provider == "safe_browsing":
            threats = data.get("threats", [])
            values = [item.get("threatType", "") for item in threats if isinstance(item, dict)]
        else:
            threat = data.get("threat", {})
            values = threat.get("threatTypes", []) if isinstance(threat, dict) else []
        return sorted({value for value in values if isinstance(value, str) and value})

    @staticmethod
    def _result(provider: str, threat_types: list[str]) -> LayerResult:
        provider_name = "Google Safe Browsing" if provider == "safe_browsing" else "Google Web Risk"
        if not threat_types:
            return LayerResult(
                layer="GOOGLE_URL_REPUTATION",
                verdict="clean",
                confidence=0.85,
                evidence_grade="observed",
                user_facing_reason=f"{provider_name} 未回報此網址的已知威脅",
                status="ok",
            )
        threat_text = "、".join(threat_types)
        signal = Signal(
            id="google_url_reputation_match",
            detail=f"{provider_name} 回報此網址含已知威脅：{threat_text}",
            grade="observed",
            weight=35,
        )
        return LayerResult(
            layer="GOOGLE_URL_REPUTATION",
            verdict="suspicious",
            score=signal.weight,
            confidence=0.9,
            evidence_grade="observed",
            signals=[signal],
            user_facing_reason=signal.detail,
            status="ok",
        )

    @staticmethod
    def _expiry(provider: str, data: dict) -> datetime:
        if provider == "safe_browsing":
            duration = data.get("cacheDuration", "")
            match = re.fullmatch(r"(\d+)(?:\.\d+)?s", duration) if isinstance(duration, str) else None
            if match:
                return datetime.now(UTC) + timedelta(seconds=max(1, int(match.group(1))))
        else:
            threat = data.get("threat", {})
            expiry = threat.get("expireTime") if isinstance(threat, dict) else None
            if isinstance(expiry, str):
                try:
                    return datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                except ValueError:
                    pass
        return datetime.now(UTC) + timedelta(minutes=5)

    @staticmethod
    def _skipped(reason: str) -> LayerResult:
        return LayerResult(layer="GOOGLE_URL_REPUTATION", status="skipped", user_facing_reason=reason)
