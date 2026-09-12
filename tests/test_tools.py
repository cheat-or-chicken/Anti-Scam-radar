import socket

import pytest

from script.config import Settings
from script.models import PageContext
from script.network import NetworkPolicyError, SafeFetcher, public_addresses
from script.tools import TOOL_NAMES, VerificationTools


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1", "192.168.0.1", "0.0.0.0"]
)
def test_ssrf_private_resolution(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(None, None, None, None, (ip, 443))])
    with pytest.raises(NetworkPolicyError):
        public_addresses("example.com", 443)


def test_mixed_public_private_dns_rejected(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [(None, None, None, None, (ip, 443)) for ip in ["8.8.8.8", "127.0.0.1"]],
    )
    with pytest.raises(NetworkPolicyError):
        public_addresses("example.com", 443)


def test_network_defaults_off():
    with pytest.raises(NetworkPolicyError):
        SafeFetcher(Settings()).get("https://example.com")


@pytest.mark.parametrize("name", TOOL_NAMES)
async def test_all_tool_entrypoints_return_status(name):
    tools = VerificationTools(Settings())
    r = await tools.call(name, PageContext(url="https://example.com"))
    assert r["status"] in {"ok", "unknown"}


async def test_tool_budget_and_unrecognized_name():
    tools = VerificationTools(Settings(max_tool_calls=1))
    ctx = PageContext(url="https://example.com")
    assert (await tools.call("__init__", ctx))["reason"] == "tool_not_allowed"
    assert (await tools.call("psl_resolve", ctx))["status"] == "ok"
    assert (await tools.call("psl_resolve", ctx))["reason"] == "tool_budget_exhausted"


async def test_rdap_parsing(monkeypatch):
    tools = VerificationTools(Settings())

    async def fake_get(*a, **kw):
        return {"text": '{"events":[{"eventAction":"registration","eventDate":"2020-01-01T00:00:00Z"}]}'}

    monkeypatch.setattr(tools, "_get", fake_get)
    assert (await tools.call("rdap_lookup", PageContext(url="https://example.com")))["domain_age_days"] > 1000


def test_redirect_to_private_is_checked_before_second_connection(monkeypatch):
    import script.network as network

    dns_calls = []

    def addresses(hostname, port):
        dns_calls.append(hostname)
        if hostname == "127.0.0.1":
            raise NetworkPolicyError("private")
        return ["8.8.8.8"]

    class Sock:
        def close(self):
            pass

    class Response:
        status = 302

        def getheader(self, name, default=None):
            return "http://127.0.0.1/admin" if name == "Location" else default

    class Connection:
        def __init__(self, *a, **kw):
            pass

        def request(self, *a, **kw):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            pass

    connects = []

    def connect(address, **kwargs):
        connects.append(address)
        return Sock()

    monkeypatch.setattr(network, "public_addresses", addresses)
    monkeypatch.setattr(network.socket, "create_connection", connect)
    monkeypatch.setattr(network.http.client, "HTTPConnection", Connection)
    with pytest.raises(NetworkPolicyError):
        SafeFetcher(Settings(network_enabled=True)).get("http://example.com")
    assert dns_calls == ["example.com", "127.0.0.1"]
    assert connects == [("8.8.8.8", 80)]
