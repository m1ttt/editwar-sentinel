import asyncio
import json

import pytest

from editwar_detector.health import HealthServer


@pytest.fixture
async def server():
    health = HealthServer(lambda: {"status": "ok", "processed": 7}, host="127.0.0.1", port=0)
    await health.start()
    yield health
    await health.stop()


async def request(port, raw):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(raw)
    await writer.drain()
    data = await reader.read()
    writer.close()
    await writer.wait_closed()
    head, _, body = data.partition(b"\r\n\r\n")
    return head.decode(), body


async def test_healthz_returns_stats(server):
    head, body = await request(server.port, b"GET /healthz HTTP/1.1\r\nHost: x\r\n\r\n")
    assert head.startswith("HTTP/1.1 200 OK")
    assert "Content-Type: application/json" in head
    assert json.loads(body) == {"status": "ok", "processed": 7}


async def test_healthz_ignores_query_string(server):
    head, _ = await request(server.port, b"GET /healthz?probe=1 HTTP/1.1\r\n\r\n")
    assert head.startswith("HTTP/1.1 200 OK")


@pytest.mark.parametrize(
    "raw",
    [
        b"GET / HTTP/1.1\r\n\r\n",
        b"POST /healthz HTTP/1.1\r\nContent-Length: 0\r\n\r\n",
        b"\r\n",
    ],
)
async def test_other_requests_return_404(server, raw):
    head, body = await request(server.port, raw)
    assert head.startswith("HTTP/1.1 404 Not Found")
    assert json.loads(body) == {"error": "not found"}


async def test_client_that_closes_early(server):
    _, writer = await asyncio.open_connection("127.0.0.1", server.port)
    writer.close()
    await writer.wait_closed()
    # The server is still healthy afterwards.
    head, _ = await request(server.port, b"GET /healthz HTTP/1.1\r\n\r\n")
    assert head.startswith("HTTP/1.1 200 OK")


async def test_slow_client_times_out(monkeypatch):
    monkeypatch.setattr("editwar_detector.health.READ_TIMEOUT_SECONDS", 0.05)
    health = HealthServer(dict, host="127.0.0.1", port=0)
    await health.start()
    reader, writer = await asyncio.open_connection("127.0.0.1", health.port)
    assert await reader.read() == b""  # closed without an answer
    writer.close()
    await health.stop()
    await health.stop()  # a second stop does nothing
