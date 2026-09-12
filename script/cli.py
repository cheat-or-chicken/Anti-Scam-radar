import argparse
import asyncio
import json
from pathlib import Path

from script.config import Settings
from script.extract import extract_page
from script.layers import REGISTRY
from script.models import PageContext
from script.pipeline import analyze
from script.storage import Store
from script.tools import TOOL_NAMES, VerificationTools


def main():
    parser = argparse.ArgumentParser(description="防詐工具驗證：預設離線、不上傳網頁內容")
    parser.add_argument("--config", default="config/config.local.json")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("analyze", "layer", "tool"):
        cmd = sub.add_parser(name)
        cmd.add_argument("input", help="PageContext JSON file")
        if name == "analyze":
            cmd.add_argument("--deep", action="store_true")
            cmd.add_argument("--screenshot", help="JPEG/PNG screenshot to send to the LLM for visual review")
        elif name == "layer":
            cmd.add_argument("name", choices=list(REGISTRY) + ["L17"])
        else:
            cmd.add_argument("name", choices=TOOL_NAMES)
    html = sub.add_parser("extract")
    html.add_argument("input")
    html.add_argument("--url", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("url", help="HTTP(S) URL to render in an ephemeral headless browser")
    scan.add_argument("--screenshot", action="store_true", help="send the captured viewport to the LLM")
    scan.add_argument("--deep", action="store_true")
    serve = sub.add_parser("serve", help="run the loopback bridge for the Chrome extension")
    serve.add_argument("--port", type=int, default=8765)
    replay = sub.add_parser("replay")
    replay.add_argument("audit_id")
    args = parser.parse_args()
    settings = Settings.load(args.config)
    if args.command == "serve":
        from script.server import serve as serve_extension

        try:
            serve_extension(settings, args.port)
        except (OSError, ValueError) as exc:
            parser.exit(2, f"Invalid input/configuration: {type(exc).__name__}\n")
        return

    async def run():
        if args.command == "replay":
            return Store(settings.database_path).replay(args.audit_id)
        if args.command == "scan":
            from script.capture import capture_website

            capture = await capture_website(
                args.url, settings.screenshot_timeout_seconds, capture_screenshot=args.screenshot
            )
            return (
                await analyze(
                    capture.context,
                    settings,
                    deep=args.deep,
                    screenshot=capture.screenshot,
                )
            ).model_dump()
        path = Path(args.input)
        if path.stat().st_size > 2_000_000:
            raise ValueError("input exceeds 2 MB")
        if args.command == "extract":
            return extract_page(args.url, path.read_text(encoding="utf-8")).model_dump()
        ctx = PageContext.model_validate_json(path.read_text(encoding="utf-8"))
        if args.command == "analyze":
            screenshot = None
            if args.screenshot:
                screenshot = Path(args.screenshot).read_bytes()
            return (await analyze(ctx, settings, deep=args.deep, screenshot=screenshot)).model_dump()
        if args.command == "layer":
            if args.name == "L7":
                from script.layers.code_review import verify_l7
                from script.llm import LLM

                llm = LLM(settings)
                try:
                    return (await verify_l7(ctx, llm)).model_dump()
                finally:
                    await llm.close()
            if args.name == "L17":
                return (await analyze(ctx, settings)).layers[-1].model_dump()
            return REGISTRY[args.name](ctx).model_dump()
        return await VerificationTools(settings, Store(settings.database_path)).call(args.name, ctx)

    try:
        print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))
    except (RuntimeError, ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"Invalid input/configuration: {type(exc).__name__}\n")


if __name__ == "__main__":
    main()
