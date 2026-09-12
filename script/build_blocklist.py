"""Reproducible CSV/JSON import, replacing the extension's Windows-specific builder."""

import argparse
import csv
import hashlib
import io
import ipaddress
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from script.blocklist import digit_skeleton
from script.domains import _extract, host


def build(source_dir: Path) -> dict:
    domains = {}
    dates = []

    def add(raw, source):
        try:
            name = host(raw.strip() if "://" in raw else "https://" + raw.strip())
            # Never promote a public suffix / shared platform into a block target.
            try:
                address = ipaddress.ip_address(name)
                if not address.is_global:
                    return
            except ValueError:
                parsed = _extract(name)
                if not parsed.domain or not parsed.suffix:
                    return
            domains.setdefault(name, {"s": []})
            if source not in domains[name]["s"]:
                domains[name]["s"].append(source)
        except (ValueError, UnicodeError):
            return

    csv_path = source_dir / "NPA_WEBURL.csv"
    json_path = source_dir / "通報TWNIC詐騙網址彙整表.json"
    raw_csv = csv_path.read_bytes()
    for encoding in ("utf-8-sig", "cp950"):
        try:
            csv_text = raw_csv.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("NPA CSV must be UTF-8 or CP950 encoded")
    for row in csv.DictReader(io.StringIO(csv_text, newline="")):
        add(row.get("網址", ""), "NPA")
        if row.get("統計結束日期"):
            dates.append(row["統計結束日期"])
    for row in json.loads(json_path.read_text(encoding="utf-8")):
        add(row.get("網域名稱", ""), "TWNIC")
    skeletons = defaultdict(list)
    for name in sorted(domains):
        skeleton = digit_skeleton(name)
        if skeleton:
            skeletons[skeleton].append(name)
    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "count": len(domains),
        "sourcePeriodEnd": max(dates) if dates else None,
        "sources": {
            "NPA": "Imported NPA_WEBURL.csv",
            "TWNIC": "Imported TWNIC dataset; source freshness unverified",
        },
        "sourceHashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (csv_path, json_path)},
        "domains": dict(sorted(domains.items())),
        "digitSkeletons": {key: value for key, value in skeletons.items() if len(value) >= 2},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=Path("extension"))
    parser.add_argument("--output", type=Path, default=Path("script/data/blocklist.json"))
    args = parser.parse_args()
    data = build(args.source_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(
        json.dumps(
            {
                "domains": data["count"],
                "digit_groups": len(data["digitSkeletons"]),
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
