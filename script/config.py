import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr = SecretStr("")
    model: str = "gpt-5.4-mini"
    code_model: str = "gpt-5.4-mini"
    vision_model: str = "gpt-5.4-mini"
    llm_enabled: bool = False
    allow_content_upload: bool = False
    network_enabled: bool = False
    google_url_reputation_provider: Literal["none", "safe_browsing", "web_risk"] = "none"
    google_url_reputation_api_key: SecretStr = SecretStr("")
    safe_browsing_enabled: bool = False
    google_safe_browsing_api_key: SecretStr = SecretStr("")
    timeout_seconds: float = Field(default=12, ge=1, le=60)
    screenshot_timeout_seconds: float = Field(default=15, ge=1, le=60)
    max_llm_calls: int = Field(default=6, ge=0, le=20)
    max_tool_calls: int = Field(default=8, ge=0, le=20)
    max_output_tokens: int = Field(default=1600, ge=128, le=8192)
    max_response_bytes: int = Field(default=1048576, ge=1024, le=2097152)
    database_path: str = "var/radar.sqlite3"
    audit_enabled: bool = True

    @classmethod
    def load(cls, path: str = "config/config.local.json") -> "Settings":
        data = json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}
        data = {"llm_enabled": True, "allow_content_upload": True, "network_enabled": True,
                "safe_browsing_enabled": True, "google_url_reputation_provider": "safe_browsing", **data}
        if not data.get("google_url_reputation_api_key") and data.get("google_safe_browsing_api_key"):
            data["google_url_reputation_api_key"] = data["google_safe_browsing_api_key"]
        if os.getenv("OPENAI_API_KEY"):
            data["api_key"] = os.environ["OPENAI_API_KEY"]
        if os.getenv("GOOGLE_URL_REPUTATION_API_KEY"):
            data["google_url_reputation_api_key"] = os.environ["GOOGLE_URL_REPUTATION_API_KEY"]
        return cls.model_validate(data)
