"""Ephemeral, headless-browser capture for an explicitly requested website scan."""

from dataclasses import dataclass

from script.domains import parse_url
from script.extract import extract_page
from script.models import PageContext
from script.vision import MAX_SCREENSHOT_BYTES


@dataclass(frozen=True)
class Capture:
    context: PageContext
    screenshot: bytes | None


async def capture_website(url: str, timeout_seconds: float, *, capture_screenshot: bool = True) -> Capture:
    """Render one user-supplied HTTP(S) URL without downloads or persistent browser state."""
    parse_url(url)
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("browser_extra_not_installed") from exc

    timeout_ms = int(timeout_seconds * 1000)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-proxy-server"])
        try:
            context = await browser.new_context(
                viewport={"width": 1440, "height": 1200},
                device_scale_factor=1,
                accept_downloads=False,
                service_workers="block",
            )
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_timeout(min(750, timeout_ms // 4))
                final_url = page.url
                parse_url(final_url)
                html = await page.content()
                screenshot = None
                if capture_screenshot:
                    screenshot = await page.screenshot(
                        type="jpeg", quality=80, full_page=False, animations="disabled", timeout=timeout_ms
                    )
            finally:
                await context.close()
        finally:
            await browser.close()

    if screenshot is not None and len(screenshot) > MAX_SCREENSHOT_BYTES:
        raise ValueError("screenshot exceeds 5 MB")
    return Capture(context=extract_page(final_url, html), screenshot=screenshot)
