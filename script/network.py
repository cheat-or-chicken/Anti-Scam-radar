"""Bounded public HTTP(S) GET. DNS is resolved once and connections pin that IP."""

import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import urljoin, urlunsplit

from script.config import Settings
from script.domains import host, parse_url


class NetworkPolicyError(ValueError):
    pass


def public_addresses(hostname: str, port: int) -> list[str]:
    addresses = list(
        dict.fromkeys(row[4][0] for row in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM))
    )
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise NetworkPolicyError("destination resolves to a non-public address")
    return addresses


class SafeFetcher:
    def __init__(self, settings: Settings):
        self.settings = settings

    def get(self, url: str, headers: dict | None = None) -> dict:
        if not self.settings.network_enabled:
            raise NetworkPolicyError("network_disabled")
        deadline = time.monotonic() + self.settings.timeout_seconds
        redirects = []
        for _ in range(6):
            parsed = parse_url(url)
            hostname = host(url)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            # Validate every redirect before connecting; never use environment proxy settings.
            addresses = public_addresses(hostname, port)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("fetch deadline exceeded")
            conn = http.client.HTTPConnection(hostname, port, timeout=remaining)
            sock = socket.create_connection((addresses[0], port), timeout=remaining)
            try:
                if parsed.scheme == "https":
                    sock = ssl.create_default_context().wrap_socket(sock, server_hostname=hostname)
                conn.sock = sock
                path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
                request_headers = {"User-Agent": "AntiScamRadar/0.1", "Accept-Encoding": "identity"}
                request_headers.update(headers or {})
                conn.request("GET", path, headers=request_headers)
                response = conn.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader("Location")
                    if not location:
                        raise NetworkPolicyError("redirect without location")
                    redirects.append(url)
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    raise NetworkPolicyError(f"upstream_status_{response.status}")
                if response.getheader("Content-Encoding", "identity") != "identity":
                    raise NetworkPolicyError("compressed responses not accepted")
                body = bytearray()
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("fetch deadline exceeded")
                    sock.settimeout(remaining)
                    chunk = response.read1(min(65536, self.settings.max_response_bytes + 1 - len(body)))
                    if not chunk:
                        break
                    body.extend(chunk)
                    if len(body) > self.settings.max_response_bytes:
                        raise NetworkPolicyError("response too large")
                return {
                    "url": url,
                    "redirects": redirects,
                    "text": body.decode("utf-8", errors="replace"),
                    "content_type": response.getheader("Content-Type", ""),
                    "tls_valid": parsed.scheme == "https",
                }
            finally:
                conn.close()
                sock.close()
        raise NetworkPolicyError("too many redirects")
