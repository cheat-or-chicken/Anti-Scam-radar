"""Bounded static investigation of a chat URL using the existing website pipeline."""

import asyncio
import threading
import time
from collections import deque
from datetime import UTC, datetime
from urllib.parse import urlsplit

from script.config import Settings
from script.extract import extract_page
from script.models import PageContext
from script.network import SafeFetcher
from script.pipeline import analyze

_slots = threading.BoundedSemaphore(2)
_lock = threading.Lock()
_cache = {}
_recent = deque()


async def inspect_link(url, settings, fetcher=None):
    ctx = PageContext(url=url, behavior="social_link")
    fetched = False
    if settings.network_enabled:
        try:
            response = await asyncio.to_thread((fetcher or SafeFetcher(settings)).get, ctx.url)
            ctx = extract_page(response["url"], response["text"])
            ctx.behavior = "social_link"
            ctx.redirects = response.get("redirects", [])
            fetched = True
        except Exception:
            pass  # Failed retrieval is unknown, never a clean verdict.
    config = settings.model_copy(
        update={
            "network_enabled": False,
            "audit_enabled": False,
            "llm_enabled": settings.llm_enabled and fetched,
            "max_llm_calls": min(4, settings.max_llm_calls),
        }
    )
    report = await analyze(ctx, config, google_settings=settings)
    decision = report.decision
    warning = decision.display_level in {"banner", "block"} or decision.risk_score > 0
    return {
        "status": "risk" if warning else "not_flagged" if fetched else "unknown",
        "score": decision.risk_score,
        "display_level": decision.display_level,
        "reasons": decision.reasons,
        "final_host": urlsplit(ctx.url).hostname,
        "fetch_status": "static_html" if fetched else "unavailable",
        "checked_at": datetime.now(UTC).isoformat(),
        "incomplete_checks": [
            layer.layer for layer in report.layers if layer.status in {"missing", "error", "skipped"}
        ],
        "notice": "僅讀取公開 HTML，不執行 JS、不登入、不提交表單；未發現警訊不代表安全。",
    }


def check_link(url):
    PageContext(url=url)  # URL validation also excludes credentials and unsupported schemes.
    now = time.monotonic()
    with _lock:
        cached = _cache.get(url)
        if cached and cached[0] > now:
            return {**cached[1], "cached": True}
    if not _slots.acquire(blocking=False):
        raise BlockingIOError("link_check_busy")
    try:
        with _lock:
            while _recent and _recent[0] < now - 60:
                _recent.popleft()
            if len(_recent) >= 30:
                raise BlockingIOError("link_check_rate_limited")
            _recent.append(now)
        settings = Settings.load()
        result = asyncio.run(inspect_link(url, settings))
        with _lock:
            if len(_cache) >= 256:
                _cache.pop(next(iter(_cache)))
            _cache[url] = (time.monotonic() + (300 if result["status"] != "unknown" else 15), result)
        return result
    finally:
        _slots.release()
