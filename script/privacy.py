"""Shared text redaction. Images and navigation metadata have separate semantics."""
import json
import re
from pathlib import Path

PATTERNS = [(re.compile(item["pattern"], re.IGNORECASE), item["replacement"])
            for item in json.loads((Path(__file__).parent / "data/privacy_patterns.json").read_text())]
SECRET_KEYS = {"password", "passwd", "api_key", "apikey", "api-key", "access_token", "refresh_token", "secret", "密碼"}


def mask_text(value):
    for pattern, replacement in PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def mask_input(value):
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, (dict, list)):
            return json.dumps(mask_input(parsed), ensure_ascii=False)
        return mask_text(value)
    if isinstance(value, list):
        return [mask_input(item) for item in value]
    if isinstance(value, dict):
        return {key: "[SECRET]" if key.lower() in SECRET_KEYS else
                item if key in {"image_url", "type", "role", "detail"} else mask_input(item)
                for key, item in value.items()}
    return value
