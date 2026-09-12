"""Narrow investigation tools. All errors become unknown, never clean."""

import asyncio
import json
from datetime import UTC, datetime
from urllib.parse import quote

from script.config import Settings
from script.domains import host, site
from script.extract import extract_page
from script.models import PageContext
from script.network import SafeFetcher
from script.storage import Store


class VerificationTools:
    def __init__(self, settings: Settings, store: Store | None = None):
        self.fetcher = SafeFetcher(settings)
        self.settings = settings
        self.store = store
        self.calls = 0

    async def _get(self, url, headers=None):
        return await asyncio.wait_for(
            asyncio.to_thread(self.fetcher.get, url, headers), self.settings.timeout_seconds + 1
        )

    async def rdap_lookup(self, ctx: PageContext):
        # ICANN/IANA bootstrap via rdap.org; redirect target also passes SSRF checks.
        data = json.loads(
            (await self._get("https://rdap.org/domain/" + quote(site(ctx.url), safe="")))["text"]
        )
        ages = []
        for event in data.get("events", []):
            if event.get("eventAction") == "registration":
                dt = datetime.fromisoformat(event["eventDate"].replace("Z", "+00:00"))
                ages.append(max(0, (datetime.now(UTC) - dt).days))
        if not ages:
            return {"status": "unknown", "reason": "registration_date_missing"}
        return {"status": "ok", "domain_age_days": max(ages)}

    async def crt_sh_search(self, ctx):
        data = json.loads(
            (await self._get("https://crt.sh/?q=" + quote(host(ctx.url), safe="") + "&output=json"))["text"]
        )
        names = set()
        for row in data[:200]:
            names.update(row.get("name_value", "").splitlines())
        # Shared certificate is association, not proof of a scam campaign.
        return {"status": "ok", "certificate_names": sorted(names)[:100], "certificate_count": len(data)}

    async def fetch_script(self, ctx):
        # Fixed current URL avoids arbitrary LLM-selected URLs and crawl expansion.
        response = await self._get(ctx.url)
        return {
            "status": "ok",
            "scripts": extract_page(response["url"], response["text"]).scripts,
            "scope": "inline_scripts_only",
        }

    async def probe_with_ua(self, ctx):
        results = await asyncio.gather(
            *[
                self._get(ctx.url, {"User-Agent": ua})
                for ua in (
                    "Mozilla/5.0 (X11; Linux x86_64) AntiScamRadar/0.1",
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile AntiScamRadar/0.1",
                    "Googlebot AntiScamRadar/0.1",
                )
            ],
            return_exceptions=True,
        )
        texts = [extract_page(r["url"], r["text"]).text for r in results if isinstance(r, dict)]
        return {
            "status": "ok" if len(texts) >= 2 else "unknown",
            "probe_texts": texts,
            "failed_probes": sum(isinstance(r, Exception) for r in results),
        }

    async def code_review(self, ctx):
        from script.layers.code_review import verify_l7
        from script.llm import LLM

        llm = LLM(self.settings)
        try:
            review = await verify_l7(ctx, llm)
            return {
                "status": "ok" if review.status == "ok" else "unknown",
                "mode": "llm_static_code_review",
                "result": review.model_dump(),
            }
        finally:
            await llm.close()

    async def sandbox_replay(self, ctx):
        """Compatibility alias: no sandbox, no JS execution."""
        return await self.code_review(ctx)

    async def wayback_diff(self, ctx):
        # Caller supplies two snapshots; live archive discovery is intentionally separate.
        from script.layers.rules import verify_l8

        return {
            "status": "ok" if ctx.previous_sensitive_fields is not None else "unknown",
            "result": verify_l8(ctx).model_dump(),
        }

    async def query_fingerprint_db(self, ctx):
        return (
            {"status": "ok", **self.store.query_fingerprint_db(ctx.text)}
            if self.store
            else {"status": "unknown"}
        )

    async def psl_resolve(self, ctx):
        return {"status": "ok", "host": host(ctx.url), "registrable_domain": site(ctx.url)}

    async def ocr_image(self, ctx):
        return {"status": "unknown", "reason": "use_script.images.ocr_image_with_local_image"}

    async def call(self, name: str, ctx: PageContext):
        if name not in TOOL_NAMES:
            return {"status": "unknown", "reason": "tool_not_allowed"}
        if self.calls >= self.settings.max_tool_calls:
            return {"status": "unknown", "reason": "tool_budget_exhausted"}
        self.calls += 1
        try:
            return await getattr(self, name)(ctx)
        except Exception as exc:
            return {"status": "unknown", "reason": type(exc).__name__}


TOOL_NAMES = (
    "rdap_lookup",
    "crt_sh_search",
    "fetch_script",
    "probe_with_ua",
    "code_review",
    "sandbox_replay",
    "wayback_diff",
    "query_fingerprint_db",
    "psl_resolve",
    "ocr_image",
)
