"""HealthServer: /healthz answers 200 with stats, everything else 404."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from editwar_ingestor.health import HealthServer


@pytest.fixture
async def server() -> AsyncIterator[HealthServer]:
    health = HealthServer(lambda: {"received": 7}, host="127.0.0.1", port=0)
    await health.start()
    yield health
    await health.stop()


async def request(port: int, raw: bytes) -> tuple[int, dict[str, Any]]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(raw)
    await writer.drain()
    response = await reader.read()
    writer.close()
    await writer.wait_closed()
    head, _, body = response.partition(b"\r\n\r\n")
    status = int(head.split()[1])
    return status, json.loads(body)


async def test_healthz_returns_stats(server: HealthServer) -> None:
    status, body = await request(server.port, b"GET /healthz HTTP/1.1\r\nHost: x\r\n\r\n")
    assert status == 200
    assert body == {"status": "ok", "received": 7}


async def test_healthz_with_query_string(server: HealthServer) -> None:
    status, _ = await request(server.port, b"GET /healthz?probe=live HTTP/1.1\r\n\r\n")
    assert status == 200


@pytest.mark.parametrize(
    "raw",
    [b"GET / HTTP/1.1\r\n\r\n", b"POST /healthz HTTP/1.1\r\n\r\n", b"garbage\n\n"],
)
async def test_other_requests_get_404(server: HealthServer, raw: bytes) -> None:
    status, body = await request(server.port, raw)
    assert status == 404
    assert body == {"error": "not found"}


async def test_client_that_disconnects_does_not_break_the_server(server: HealthServer) -> None:
    _, writer = await asyncio.open_connection("127.0.0.1", server.port)
    writer.close()
    await writer.wait_closed()
    status, _ = await request(server.port, b"GET /healthz HTTP/1.1\r\n\r\n")
    assert status == 200


async def test_stop_twice_is_safe() -> None:
    health = HealthServer(dict, host="127.0.0.1", port=0)
    await health.start()
    await health.stop()
    await health.stop()
