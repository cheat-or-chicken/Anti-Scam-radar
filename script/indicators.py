"""Evidence inventory. Missing data and weak infrastructure facts never add risk points."""

import asyncio
import json
from datetime import UTC, datetime
from urllib.parse import quote, urlencode

from bs4 import BeautifulSoup

from script.brand_patterns import brand_patterns
from script.config import Settings
from script.domains import site
from script.models import PageContext
from script.network import SafeFetcher


def item(name, status, reason, **facts):
    return {"indicator": name, "status": status, "reason": reason, "facts": facts}


def inspect_content(ctx):
    soup = BeautifulSoup(ctx.html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    text = (ctx.text or soup.get_text(" ", strip=True)).strip()
    usable = len(text) >= 80 and not any(
        marker in text[:500].lower()
        for marker in (
            "404 not found",
            "access denied",
            "checking your browser",
            "just a moment",
            "verify you are human",
            "驗證您是否為真人",
        )
    )
    checks = [
        item(
            "content_coverage",
            "observed" if usable else "unknown",
            "取得可讀文字；仍僅涵蓋靜態內容"
            if usable
            else "內容過少、空白或疑似錯誤／驗證頁；不能據此宣稱沒有表單或詐騙話術",
            readable_characters=len(text),
        )
    ]
    if not ctx.html or not usable:
        checks += [
            item(name, "unknown", "未取得足夠可讀 HTML，不能判定未命中")
            for name in ("seo_metadata", "commerce_context", "analytics_ids")
        ]
        return checks
    meta = [
        m
        for m in soup.find_all("meta")
        if m.get("name") == "description" or str(m.get("property", "")).startswith("og:")
    ]
    checks.append(
        item(
            "seo_metadata",
            "observed",
            "僅統計 metadata，不能認證商家或網站安全；未查 robots/sitemap",
            metadata_count=len(meta),
            link_count=len(soup.find_all("a", href=True)),
        )
    )
    checks.append(
        item(
            "commerce_context",
            "observed",
            "購物車與聯絡資訊可被仿造，出現或缺少都不是商家認證",
            cart_terms=any(w in text for w in ("購物車", "加入購物", "結帳")),
            contact_terms=any(w in text for w in ("聯絡我們", "客服電話", "統一編號")),
        )
    )
    import re

    identifiers = sorted(
        set(re.findall(r"\b(?:G-[A-Z0-9]{6,15}|GTM-[A-Z0-9]{4,12}|UA-\d{4,12}-\d{1,4})\b", ctx.html))
    )[:30]
    checks.append(
        item(
            "analytics_ids",
            "observed",
            "共用分析 ID 僅供關聯調查，不能單獨證明同一詐騙站群",
            identifiers=identifiers,
            association_verified=False,
        )
    )
    return checks


async def safe_browsing(ctx, settings, fetcher):
    if not settings.network_enabled or not settings.safe_browsing_enabled:
        return item("google_safe_browsing", "unknown", "尚未啟用 Google 查詢，並非查詢未命中")
    key = settings.google_safe_browsing_api_key.get_secret_value()
    if not key:
        return item("google_safe_browsing", "unknown", "缺少 Google Safe Browsing key；OpenAI key 不能替代")
    # Separate explicit opt-in: this API transmits the full URL to Google.
    query = urlencode({"urls": ctx.url, "key": key})
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(fetcher.get, "https://safebrowsing.googleapis.com/v5/urls:search?" + query),
            settings.timeout_seconds + 1,
        )
        data = json.loads(response["text"])
        if not isinstance(data, dict) or not isinstance(data.get("cacheDuration"), str):
            raise ValueError("invalid_provider_response")
        threats = data.get("threats", [])
        if not isinstance(threats, list):
            raise ValueError("invalid_threats")
        supported = {"MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"}
        types = set()
        for threat in threats:
            values = threat["threatTypes"]
            if not isinstance(values, list) or not values or not set(values) <= supported:
                raise ValueError("unknown_threat_type")
            types.update(values)
        return item(
            "google_safe_browsing",
            "matched" if types else "not_listed",
            "Google 回報威脅，請停止敏感操作"
            if types
            else "本次 Google 查詢未命中已知威脅，不代表安全，也不抵銷其他警訊",
            threat_types=sorted(types),
            checked_at=datetime.now(UTC).isoformat(),
        )
    except Exception:
        return item("google_safe_browsing", "unknown", "Google 查詢未完成，並非查詢未命中")


async def registration(ctx, settings, fetcher):
    if not settings.network_enabled:
        return item("registration", "unknown", "網路查詢未啟用")
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(fetcher.get, "https://rdap.org/domain/" + quote(site(ctx.url), safe="")),
            settings.timeout_seconds + 1,
        )
        data = json.loads(response["text"])
        dates = {}
        for event in data.get("events", []):
            if event.get("eventAction") in {"registration", "expiration"}:
                dates[event["eventAction"]] = datetime.fromisoformat(
                    event["eventDate"].replace("Z", "+00:00")
                )
        if "registration" not in dates:
            raise ValueError("missing_registration")
        start = dates["registration"]
        now = datetime.now(UTC)
        if start > now:
            raise ValueError("future_registration")
        facts = {
            "domain": site(ctx.url),
            "registered_at": start.isoformat(),
            "age_days": (now - start).days,
            "checked_at": now.isoformat(),
        }
        if "expiration" in dates and dates["expiration"] >= start:
            facts.update(
                expires_at=dates["expiration"].isoformat(),
                registration_period_days=(dates["expiration"] - start).days,
            )
        return item(
            "registration",
            "observed",
            "註冊時間僅為背景資料；一年期、隱私保護或特定註冊商不能單獨證明詐騙",
            **facts,
        )
    except Exception:
        return item("registration", "unknown", "未取得可用 RDAP 註冊日期；不沿用外部貼文日期")


async def inspect_indicators(ctx: PageContext, settings: Settings, *, fetch_page=False, checks=()):
    fetcher = SafeFetcher(settings)
    output = [
        item(
            "brand_url",
            "suspicious" if (patterns := brand_patterns(ctx.url)) else "not_matched",
            "品牌近似只是待查證訊號；不等於人工确认黑名單",
            patterns=patterns,
        )
    ]
    if fetch_page:
        if not settings.network_enabled:
            output.append(item("http_fetch", "unknown", "網路查詢未啟用"))
            ctx = PageContext(url=ctx.url)
        else:
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(fetcher.get, ctx.url), settings.timeout_seconds + 1
                )
                if "html" not in response.get("content_type", "").lower():
                    raise ValueError("not_html")
                ctx = PageContext(url=response["url"], html=response["text"])
                output.append(item("http_fetch", "observed", "取得 HTTP HTML，未執行 JavaScript"))
                headers = response.get("security_headers", {})
                output.append(
                    item(
                        "security_headers",
                        "observed",
                        "缺少安全標頭屬於防護設定資訊，不能單獨認定詐騙",
                        present=[k for k, v in headers.items() if v],
                        missing=[k for k, v in headers.items() if not v],
                    )
                )
            except Exception:
                ctx = PageContext(url=ctx.url)
                output.append(item("http_fetch", "unknown", "抓取失敗、非 HTML 或存取被拒；不能當成乾淨頁面"))
    output.extend(inspect_content(ctx))
    tasks = {"safe_browsing": safe_browsing, "registration": registration}
    selected = list(dict.fromkeys(checks))[: settings.max_tool_calls]
    output.extend(await asyncio.gather(*(tasks[name](ctx, settings, fetcher) for name in selected)))
    for key in checks:
        if key not in selected:
            output.append(item(key, "unknown", "查詢預算不足"))
    for name in (
        "tranco",
        "mx",
        "company_registry",
        "business_identity",
        "ip_geolocation",
        "certificate_dates",
    ):
        output.append(item(name, "unknown", "尚未接入可驗證資料來源，不視為未命中或負面證據"))
    return {
        "coverage": "partial",
        "indicators": output,
        "notice": "未命中名單不等於安全；CDN／Cloudflare IP 位置不代表商家所在地。",
    }
