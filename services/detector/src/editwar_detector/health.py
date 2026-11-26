"""Minimal HTTP server for Kubernetes probes, built on asyncio.start_server.

GET /healthz answers 200 with the service stats as JSON. Every other request
answers 404.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from contextlib import suppress
from typing import Any

log = logging.getLogger("editwar.detector.health")

READ_TIMEOUT_SECONDS = 5


class HealthServer:
    """Serves GET /healthz with the dict that `stats` returns."""

    def __init__(
        self, stats: Callable[[], dict[str, Any]], host: str = "0.0.0.0", port: int = 8081
    ) -> None:
        self.stats = stats
        self.host = host
        self.port = port
        self.server: asyncio.Server | None = None

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, self.host, self.port)
        # With port 0 the system picks a free port. Keep the real one.
        self.port = self.server.sockets[0].getsockname()[1]
        log.info("health server listening on %s:%s", self.host, self.port)

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), READ_TIMEOUT_SECONDS)
            # Read and ignore the headers, up to the empty line.
            while request_line.strip():
                line = await asyncio.wait_for(reader.readline(), READ_TIMEOUT_SECONDS)
                if line in (b"\r\n", b"\n", b""):
                    break
            parts = request_line.decode("latin-1").split()
            method = parts[0] if parts else ""
            path = parts[1].split("?")[0] if len(parts) > 1 else ""
            if method == "GET" and path == "/healthz":
                writer.write(_response("200 OK", self.stats()))
            else:
                writer.write(_response("404 Not Found", {"error": "not found"}))
            await writer.drain()
        except (TimeoutError, ConnectionError) as error:
            log.debug("health request failed: %s", error)
        finally:
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()


def _response(status: str, body: dict[str, Any]) -> bytes:
    """Build a complete HTTP/1.1 response with a JSON body."""
    payload = json.dumps(body).encode()
    head = (
        f"HTTP/1.1 {status}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    return head.encode() + payload
