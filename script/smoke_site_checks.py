"""Explicit paid smoke test using synthetic content and the configured backend key."""

import asyncio
import json

import httpx

from script.config import Settings
from script.server import create_app


async def main():
    settings = Settings.load()
    if not (settings.llm_enabled and settings.allow_content_upload and settings.network_enabled):
        raise SystemExit("Enable llm_enabled, allow_content_upload and network_enabled first")
    cases = [
        (
            "verify-brand",
            "https://711-payment.example",
            "台灣 7-ELEVEN 官方繳費服務，請完成付款。",
            "match",
            "mismatch",
        ),
        (
            "verify-brand",
            "https://www.7-11.com.tw/",
            "台灣 7-ELEVEN 官方網站，統一超商歡迎您。",
            "match",
            "match",
        ),
        (
            "analyze-semantics",
            "https://example.com",
            "監理站通知：逾期罰單將凍結帳戶，請立即把信用卡资料與簡訊 OTP 傳給客服，否則強制扣款。",
            "verdict",
            "suspicious",
        ),
        (
            "analyze-semantics",
            "https://example.com",
            "防詐宣導：不要把密碼或 OTP 交給客服。詐騙者常用限時繳款威脅民眾，請自行查證官方管道。",
            "verdict",
            "clean",
        ),
        (
            "analyze-semantics",
            "https://example.com",
            "會員登入：請在本站輸入傳至您手機的驗證碼以登入。切勿將驗證碼提供給他人或客服。",
            "verdict",
            "clean",
        ),
        (
            "verify-brand",
            "https://example.com",
            "生活新聞：記者報導，台灣 7-ELEVEN 推出新品，消費者評價各異。本站為獨立新聞媒體。",
            "reason",
            "no_clear_brand_claim",
        ),
    ]
    token = "synthetic-smoke-token-" * 3
    failures = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings, token)),
        base_url="http://testserver",
        timeout=250,
        headers={"Authorization": "Bearer " + token},
    ) as client:
        for index, (route, url, text, field, expected) in enumerate(cases):
            result = await client.post("/v1/" + route, json={"context": {"url": url, "text": text}})
            data = result.json()
            passed = result.status_code == 200 and data.get(field) == expected
            print(
                json.dumps({"case": index + 1, "passed": passed, "result": data}, ensure_ascii=False),
                flush=True,
            )
            if not passed:
                failures.append(index + 1)
    if failures:
        raise SystemExit(f"Live checks differed from expectations: {failures}")


if __name__ == "__main__":
    asyncio.run(main())
