"""Loopback-only extension bridge. A pairing token is separate from the OpenAI key."""

import argparse
import asyncio
import os
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field

from script.config import Settings
from script.extract import extract_page
from script.llm import LLM
from script.models import Model, PageContext
from script.network import SafeFetcher
from script.pipeline import analyze
from script.site_checks import analyze_semantics, verify_brand


class SiteCheckRequest(Model):
    context: PageContext


class AnalyzeRequest(Model):
    context: PageContext
    include_llm: bool = False


class URLRequest(Model):
    url: str = Field(max_length=8192)
    fetch_page: bool = False
    include_llm: bool = False


def create_app(settings: Settings, token: str) -> FastAPI:
    if len(token) < 32:
        raise ValueError("pairing token must contain at least 32 characters")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    recent = deque()
    running = 0

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
            if size > 1_000_000:
                return JSONResponse({"error": "payload_too_large"}, status_code=413)
            body.extend(chunk)
        request._body = bytes(body)
        return await call_next(request)

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
            # DOM snapshots cannot attest to observed exfiltration or backend lookup facts.
            ctx = payload.context.model_copy(
                update={
                    "network_trace": [],
                    "trace_collected": False,
                    "domain_age_days": None,
                    "tls_valid": None,
                }
            )
            config = for_request(payload.include_llm).model_copy(update={"network_enabled": False})
            return await analyze(ctx, config)

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
            config = for_request(payload.include_llm).model_copy(update={"network_enabled": False})
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

    return app


def main():
    parser = argparse.ArgumentParser(description="Run the local extension backend")
    parser.add_argument("--config", default="config/config.local.json")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    token_path = Path("var/extension-token.txt")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    if not token_path.exists():
        with os.fdopen(os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            stream.write(secrets.token_urlsafe(32))
    token_path.chmod(0o600)
    print(f"Pairing token file: {token_path.resolve()} (paste into extension settings; not your API key)")
    uvicorn.run(
        create_app(Settings.load(args.config), token_path.read_text().strip()),
        host="127.0.0.1",
        port=args.port,
        access_log=False,
    )


if __name__ == "__main__":
    main()
