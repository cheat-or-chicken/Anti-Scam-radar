import ipaddress
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import idna
import tldextract

# Bundled PSL snapshot: deterministic offline behavior; PRIVATE section separates hosting tenants.
_extract = tldextract.TLDExtract(suffix_list_urls=(), include_psl_private_domains=True)


def parse_url(url: str):
    if any(ord(c) < 33 for c in url) or "\\" in url:
        raise ValueError("URL contains whitespace, controls or backslash")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("only absolute HTTP(S) URLs without credentials are supported")
    demo_loopback = parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port == 8088
    if parsed.port not in {None, 80, 443} and not demo_loopback:
        raise ValueError("only ports 80/443 are supported")
    host(url)
    return parsed


def host(url: str) -> str:
    hostname = urlsplit(url).hostname
    if not hostname:
        raise ValueError("missing host")
    hostname = hostname.rstrip(".")
    try:
        return str(ipaddress.ip_address(hostname))
    except ValueError:
        return idna.encode(hostname, uts46=True).decode("ascii").lower()


def site(url: str) -> str:
    hostname = host(url)
    extracted = _extract(hostname)
    return extracted.top_domain_under_public_suffix or hostname


def same_site(a: str, b: str) -> bool:
    return site(a) == site(b)


@lru_cache
def brands() -> list[dict]:
    return json.loads((Path(__file__).resolve().parent / "data/brands.json").read_text())


def matches_domain(hostname: str, domain: str) -> bool:
    return hostname == domain or hostname.endswith("." + domain)


def trusted(url: str) -> bool:
    return urlsplit(url).scheme == "https" and any(
        matches_domain(host(url), d) for brand in brands() for d in brand["domains"]
    )
