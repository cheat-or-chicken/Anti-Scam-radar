"""Loopback-only extension bridge. A pairing token is separate from the OpenAI key."""

import argparse
import asyncio
import base64
import binascii
import os
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field

from script.config import Settings
from script.domains import site
from script.extract import extract_page
from script.indicators import inspect_indicators
from script.llm import LLM
from script.models import Model, PageContext
from script.network import SafeFetcher
from script.pipeline import analyze
from script.progress import configure_logging, event, phase, request_id
from script.site_checks import analyze_semantics, verify_brand
from script.tools import VerificationTools
from script.vision import MAX_SCREENSHOT_BYTES, image_mime_type

MAX_REQUEST_BYTES = 7_000_000
MAX_SCREENSHOT_BASE64_CHARS = ((MAX_SCREENSHOT_BYTES + 2) // 3) * 4


class DiagnosisRequest(Model):
    audit_id: str = Field(min_length=32, max_length=32, pattern="^[a-f0-9]+$")
    confirmed_label: Literal["scam", "legitimate"]
    reviewed: bool = False


class SiteCheckRequest(Model):
    context: PageContext


class IndicatorRequest(Model):
    context: PageContext
    fetch_page: bool = False
    checks: list[Literal["safe_browsing", "registration"]] = Field(default_factory=list, max_length=2)


class AnalyzeRequest(Model):
    context: PageContext
    include_llm: bool = False
    screenshot: str | None = Field(default=None, max_length=MAX_SCREENSHOT_BASE64_CHARS)


class URLRequest(Model):
    url: str = Field(max_length=8192)
    fetch_page: bool = False
    include_llm: bool = False


def decode_screenshot(value: str | None) -> bytes | None:
    """Accept only a bounded PNG/JPEG payload from the paired extension."""
    if value is None:
        return None
    try:
        screenshot = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid screenshot encoding") from exc
    if len(screenshot) > MAX_SCREENSHOT_BYTES or image_mime_type(screenshot) is None:
        raise ValueError("invalid screenshot")
    return screenshot


def create_app(settings: Settings, token: str) -> FastAPI:
    if len(token) < 32:
        raise ValueError("pairing token must contain at least 32 characters")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    recent = deque()
    running = 0
    rdap_cache = {}

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in {"127.0.0.1", "localhost", "testserver"}:
            return JSONResponse({"error": "invalid_host"}, status_code=403)
        origin = request.headers.get("origin", "")
        if origin and not origin.startswith("chrome-extension://"):
            return JSONResponse({"error": "extension_origin_required"}, status_code=403)
        if request.url.path == "/health" and request.method == "GET":
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if not secrets.compare_digest(auth, "Bearer " + token):
            return JSONResponse({"error": "pairing_required"}, status_code=401)
        size = 0
        body = bytearray()
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_REQUEST_BYTES:
                return JSONResponse({"error": "payload_too_large"}, status_code=413)
            body.extend(chunk)
        request._body = bytes(body)
        return await call_next(request)

    @app.middleware("http")
    async def progress(request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        ident = secrets.token_hex(4)
        context_token = request_id.set(ident)
        # Only maintained route names enter logs, never user-controlled paths or queries.
        routes = {
            "/v1/analyze",
            "/v1/check-url",
            "/v1/verify-brand",
            "/v1/analyze-semantics",
            "/v1/indicators",
            "/v1/diagnose",
        }
        route = request.url.path if request.url.path in routes else "unknown_route"
        try:
            with phase(route):
                response = await call_next(request)
                event("http", str(response.status_code))
                response.headers["X-Request-ID"] = ident
                return response
        finally:
            request_id.reset(context_token)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        return JSONResponse({"error": "invalid_input"}, status_code=422)

    @asynccontextmanager
    async def budget():
        nonlocal running
        now = time.monotonic()
        while recent and recent[0] < now - 60:
            recent.popleft()
        if running >= 2 or len(recent) >= 12:
            raise HTTPException(429, "analysis_budget_exhausted")
        recent.append(now)
        running += 1
        try:
            yield
        finally:
            running -= 1

    def for_request(include_llm):
        return settings.model_copy(update={"llm_enabled": settings.llm_enabled and include_llm})

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "version": "2.0",
            "llm_configured": settings.llm_enabled and bool(settings.api_key.get_secret_value()),
        }

    @app.post("/v1/analyze")
    async def analyze_snapshot(payload: AnalyzeRequest):
        async with budget():
            try:
                screenshot = decode_screenshot(payload.screenshot)
            except ValueError:
                raise HTTPException(422, "invalid_screenshot") from None
            # DOM snapshots cannot attest to observed exfiltration or backend lookup facts.
            ctx = payload.context.model_copy(
                update={
                    "network_trace": [],
                    "trace_collected": False,
                    "domain_age_days": None,
                    "tls_valid": None,
                }
            )
            registration_error = None
            if settings.network_enabled:
                domain = site(ctx.url)
                cached = rdap_cache.get(domain)
                if cached and cached[0] > time.monotonic():
                    registration = cached[1]
                    event("L5.rdap", "cache_hit")
                else:
                    lookup_settings = settings.model_copy(
                        update={"timeout_seconds": min(8, settings.timeout_seconds)}
                    )
                    with phase("L5.rdap"):
                        registration = await VerificationTools(lookup_settings).call("rdap_lookup", ctx)
                    event("L5.rdap.result", "ok" if registration.get("status") == "ok" else "unknown")
                    if len(rdap_cache) >= 256:
                        rdap_cache.pop(next(iter(rdap_cache)))
                    rdap_cache[domain] = (time.monotonic() + 300, registration)
                if registration.get("status") == "ok":
                    ctx = ctx.model_copy(update={"domain_age_days": registration["domain_age_days"]})
                else:
                    registration_error = "已嘗試 RDAP 查詢，但未取得註冊日期；其他檢查不受影響。"
            config = for_request(payload.include_llm).model_copy(update={"network_enabled": False})
            analysis = await analyze(
                ctx,
                config,
                **(
                    {"google_settings": settings} if settings.google_url_reputation_provider != "none" else {}
                ),
                **({"screenshot": screenshot} if screenshot is not None else {}),
            )
            if not config.llm_enabled or not config.allow_content_upload:
                review = next(entry for entry in analysis.layers if entry.layer == "L7")
                review.status = "skipped"
                review.user_facing_reason = (
                    "AI 審查未啟用：需擴充功能 AI 許可及後端 llm_enabled、allow_content_upload。"
                )
            if registration_error:
                layer = next(entry for entry in analysis.layers if entry.layer == "L5")
                layer.user_facing_reason = registration_error
                layer.status = "error"
            return analysis

    @app.post("/v1/check-url")
    async def check_url(payload: URLRequest):
        async with budget():
            try:
                ctx = PageContext(url=payload.url)
            except ValueError:
                raise HTTPException(422, "invalid_url") from None
            fetch_status = "not_requested"
            if payload.fetch_page:
                if not settings.network_enabled:
                    fetch_status = "network_disabled"
                else:
                    try:
                        response = await asyncio.wait_for(
                            asyncio.to_thread(SafeFetcher(settings).get, ctx.url),
                            settings.timeout_seconds + 1,
                        )
                        ctx = extract_page(response["url"], response["text"])
                        ctx.redirects = response["redirects"]
                        fetch_status = "http_only_no_javascript"
                    except Exception:
                        fetch_status = "unavailable"
            # Keep the extension's normal analysis offline, except for the explicit Google URL lookup.
            config = for_request(payload.include_llm).model_copy(
                update={
                    "network_enabled": settings.network_enabled
                    and settings.google_url_reputation_provider != "none"
                }
            )
            analysis = await analyze(ctx, config)
            parsed = urlsplit(ctx.url)
            return {
                "analysis": analysis,
                "fetch_status": fetch_status,
                "final_url": f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
                "redirect_count": len(ctx.redirects),
            }

    async def site_check(payload, check):
        async with budget():
            llm = LLM(settings)
            try:
                return await check(payload.context, llm)
            finally:
                await llm.close()

    @app.post("/v1/verify-brand")
    async def brand_endpoint(payload: SiteCheckRequest):
        return await site_check(payload, verify_brand)

    @app.post("/v1/analyze-semantics")
    async def semantics_endpoint(payload: SiteCheckRequest):
        return await site_check(payload, analyze_semantics)

    @app.post("/v1/diagnose")
    async def diagnose_endpoint(payload: DiagnosisRequest):
        if not payload.reviewed:
            raise HTTPException(422, "human_confirmation_required")
        if not settings.allow_content_upload or not settings.llm_enabled:
            raise HTTPException(409, "llm_disabled")
        from script.storage import Store
        from script.workflow import diagnose

        async with budget():
            try:
                prior = Store(settings.database_path).replay(payload.audit_id)
            except (KeyError, TypeError):
                raise HTTPException(404, "audit_not_found") from None
            llm = LLM(settings)
            try:
                return await diagnose(prior, payload.confirmed_label, llm)
            except Exception:
                raise HTTPException(502, "diagnosis_unavailable") from None
            finally:
                await llm.close()

    @app.post("/v1/indicators")
    async def indicator_endpoint(payload: IndicatorRequest):
        async with budget():
            return await inspect_indicators(
                payload.context, settings, fetch_page=payload.fetch_page, checks=payload.checks
            )

    return app


def serve(settings: Settings, port: int = 8765, log_file: str = "var/backend.log") -> None:
    """Run the main extension backend for the CLI's compatibility command."""
    configure_logging(log_file)
    event("backend", "starting")
    token_path = Path("var/extension-token.txt")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    if not token_path.exists():
        with os.fdopen(os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            stream.write(secrets.token_urlsafe(32))
    token_path.chmod(0o600)
    print(f"Pairing token file: {token_path.resolve()} (paste into extension settings; not your API key)")
    uvicorn.run(
        create_app(settings, token_path.read_text(encoding="utf-8").strip()),
        host="127.0.0.1",
        port=port,
        access_log=False,
    )


def main():
    parser = argparse.ArgumentParser(description="Run the local extension backend")
    parser.add_argument("--config", default="config/config.local.json")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--log-file", default="var/backend.log")
    args = parser.parse_args()
    serve(Settings.load(args.config), args.port, args.log_file)


if __name__ == "__main__":
    main()
