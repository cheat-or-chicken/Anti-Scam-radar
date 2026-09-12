"""Package only loadable extension assets, never repositories, raw datasets or secrets."""

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ASSETS = [
    "manifest.json",
    "background.js",
    "content.js",
    "popup.html",
    "popup.js",
    "options.html",
    "options.js",
    "warning.html",
    "warning.js",
    "ui.css",
    "blocklist.json",
    "README.md",
    "THIRD_PARTY_NOTICES.txt",
]


def package(source: Path, output: Path):
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest["manifest_version"] != 3:
        raise ValueError("Manifest V3 required")
    paths = [source / name for name in [*ASSETS, *manifest.get("icons", {}).values()]]
    if not all(p.is_file() for p in paths):
        raise ValueError("missing build assets; run npm --prefix extension run build first")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, str(path.relative_to(source)))
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("extension"))
    parser.add_argument("--output", type=Path, default=Path("var/anti-scam-radar-extension.zip"))
    args = parser.parse_args()
    print(package(args.source, args.output).resolve())


if __name__ == "__main__":
    main()
