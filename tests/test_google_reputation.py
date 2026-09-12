from script.config import Settings
from script.google_reputation import GoogleUrlReputation
from script.models import PageContext


class FakeFetcher:
    def __init__(self, body: str):
        self.body = body
        self.urls: list[str] = []

    def get(self, url: str) -> dict:
        self.urls.append(url)
        return {"text": self.body}


async def test_safe_browsing_match_adds_observed_signal_without_exposing_key():
    GoogleUrlReputation._cache.clear()
    fetcher = FakeFetcher('{"threats": [{"threatTypes": ["SOCIAL_ENGINEERING"]}], "cacheDuration": "300s"}')
    settings = Settings(
        network_enabled=True,
        google_url_reputation_provider="safe_browsing",
        google_url_reputation_api_key="test-google-key",
    )

    result = await GoogleUrlReputation(settings, fetcher).check(
        PageContext(url="https://safe-test.example/path")
    )

    assert result.status == "ok"
    assert result.verdict == "suspicious"
    assert result.signals[0].grade == "observed"
    assert "SOCIAL_ENGINEERING" in result.user_facing_reason
    assert "test-google-key" not in result.model_dump_json()
    assert "urls%5B%5D=https%3A%2F%2Fsafe-test.example%2Fpath" in fetcher.urls[0]


async def test_web_risk_empty_response_is_clean_and_requests_all_supported_threat_types():
    GoogleUrlReputation._cache.clear()
    fetcher = FakeFetcher("{}")
    settings = Settings(
        network_enabled=True,
        google_url_reputation_provider="web_risk",
        google_url_reputation_api_key="test-google-key",
    )

    result = await GoogleUrlReputation(settings, fetcher).check(PageContext(url="https://risk-test.example"))

    assert result.status == "ok"
    assert result.verdict == "clean"
    assert fetcher.urls[0].count("threatTypes=") == 3


async def test_reputation_lookup_is_skipped_without_network_or_key():
    no_network = Settings(
        google_url_reputation_provider="web_risk", google_url_reputation_api_key="test-google-key"
    )
    missing_key = Settings(network_enabled=True, google_url_reputation_provider="web_risk")

    no_network_result = await GoogleUrlReputation(no_network).check(
        PageContext(url="https://network-test.example")
    )
    missing_key_result = await GoogleUrlReputation(missing_key).check(
        PageContext(url="https://key-test.example")
    )

    assert no_network_result.status == "skipped"
    assert missing_key_result.status == "skipped"


async def test_invalid_threat_response_never_claims_clean():
    GoogleUrlReputation._cache.clear()
    settings = Settings(
        network_enabled=True,
        google_url_reputation_provider="safe_browsing",
        google_url_reputation_api_key="test",
    )
    for body in ['{"threats":[{"threatType":"MALWARE"}],"cacheDuration":"300s"}', "{}"]:
        result = await GoogleUrlReputation(settings, FakeFetcher(body)).check(
            PageContext(url="https://invalid.example")
        )
        assert result.status == "error"


def test_loaded_defaults_enable_features_but_explicit_disable_is_respected(tmp_path):
    config = tmp_path / "config.json"
    defaults = Settings.load(str(config))
    assert defaults.llm_enabled and defaults.allow_content_upload and defaults.network_enabled
    assert defaults.google_url_reputation_provider == "safe_browsing"
    config.write_text('{"llm_enabled": false}')
    assert not Settings.load(str(config)).llm_enabled
