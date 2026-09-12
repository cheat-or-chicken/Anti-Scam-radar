import logging

import httpx

from script.config import Settings
from script.progress import request_id
from script.server import create_app


async def test_request_logs_progress_without_private_data(caplog):
    token = "private-pairing-value-" * 3
    with caplog.at_level(logging.INFO, logger="radar.progress"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(Settings(audit_enabled=False), token)),
            base_url="http://testserver",
        ) as client:
            result = await client.post(
                "/v1/analyze?private-query=secret",
                headers={"Authorization": "Bearer " + token},
                json={
                    "context": {
                        "url": "https://example.com/private-account?secret=abc",
                        "text": "PRIVATE_PAGE_TEXT",
                    },
                    "include_llm": False,
                },
            )
    assert result.status_code == 200
    assert len(result.headers["X-Request-ID"]) == 8
    assert "stage=L1.rules status=started" in caplog.text
    assert "stage=adjudication status=finished" in caplog.text
    assert "stage=http status=200" in caplog.text
    for value in [token, "PRIVATE_PAGE_TEXT", "private-account", "private-query", "secret=abc"]:
        assert value not in caplog.text
    assert request_id.get() == "-"


async def test_rejected_request_gets_status_log_without_credentials(caplog):
    with caplog.at_level(logging.INFO, logger="radar.progress"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(Settings(), "a" * 32)), base_url="http://testserver"
        ) as client:
            result = await client.post("/v1/analyze", headers={"Authorization": "Bearer SECRET"})
    assert result.status_code == 401
    assert "stage=http status=401" in caplog.text
    assert "SECRET" not in caplog.text
