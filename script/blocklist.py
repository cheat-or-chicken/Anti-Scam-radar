"""Imported extension features: normalized blocklist and conservative digit variants."""

import json
import re
from functools import lru_cache
from pathlib import Path

from script.domains import host, site
from script.models import PageContext, Signal, result


def digit_skeleton(hostname: str) -> str | None:
    if not re.search(r"\d", hostname) or any(label.isdigit() for label in hostname.split(".")):
        return None
    return re.sub(r"\d+", "#", hostname)


class Blocklist:
    def __init__(self, data: dict):
        self.domains = data.get("domains", {})
        self.skeletons = data.get("digitSkeletons", {})
        self.metadata = {key: data.get(key) for key in ("generatedAt", "count", "sourcePeriodEnd", "sources")}

    def check(self, url: str) -> dict:
        hostname = host(url)
        boundary = site(url)
        candidate = hostname
        while True:
            if candidate in self.domains:
                row = self.domains[candidate]
                return {
                    "matched": True,
                    "matched_domain": candidate,
                    "sources": row.get("s", []),
                    "kind": "listed",
                    "similar_to": [],
                }
            if candidate == boundary or "." not in candidate:
                break
            candidate = candidate.split(".", 1)[1]
        skeleton = digit_skeleton(hostname)
        matches = self.skeletons.get(skeleton, []) if skeleton else []
        return {"matched": False, "kind": "similar" if matches else "none", "similar_to": matches[:3]}


@lru_cache
def bundled_blocklist() -> Blocklist:
    return Blocklist(json.loads((Path(__file__).parent / "data/blocklist.json").read_text(encoding="utf-8")))


def verify_blocklist(ctx: PageContext):
    try:
        db = bundled_blocklist()
        checks = [db.check(url) for url in [*ctx.redirects, ctx.url]]
        listed = next((check for check in checks if check["matched"]), None)
        signals = []
        if listed:
            signals.append(
                Signal(
                    id="listed_domain",
                    detail="目前網址或轉址鏈命中匯入的 NPA／TWNIC 通報名單，建議停止瀏覽並查證",
                    weight=100,
                    grade="observed",
                    hard=True,
                )
            )
        elif any(check["kind"] == "similar" for check in checks):
            signals.append(
                Signal(
                    id="digit_variant",
                    detail="網址與通報名單中的網域僅有數字差異，尚未確認為同一網站",
                    weight=20,
                )
            )
        return result("BLOCKLIST", signals)
    except (OSError, ValueError):
        return result("BLOCKLIST", [], available=False)
