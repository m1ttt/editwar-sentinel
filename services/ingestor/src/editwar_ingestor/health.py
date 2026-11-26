"""A tiny HTTP server for the Kubernetes probes. It uses only asyncio."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("editwar.ingestor.health")

REASONS = {200: "OK", 404: "Not Found"}


class HealthServer:
    """Answer GET /healthz with 200 and the service stats as JSON. Anything else gets 404."""

    def __init__(
        self, stats: Callable[[], dict[str, Any]], host: str = "0.0.0.0", port: int = 8081
    ) -> None:
        self.stats = stats
        self.host = host
        self.port = port  # with port 0 the system picks a free port, start() stores it here
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        """Start listening."""
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        logger.info("health server listening on %s:%d", self.host, self.port)

    async def stop(self) -> None:
        """Stop listening."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Read one request and write one response."""
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=5)
            # Read and ignore the headers, which end with an empty line.
            while True:
                header = await asyncio.wait_for(reader.readline(), timeout=5)
                if header in (b"\r\n", b"\n", b""):
                    break
            status, body = self._route(request_line.decode("latin-1"))
            writer.write(_response(status, body))
            await writer.drain()
        except (TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()

    def _route(self, request_line: str) -> tuple[int, dict[str, Any]]:
        """Choose the status code and body for a request line such as 'GET /healthz HTTP/1.1'."""
        parts = request_line.split()
        if len(parts) >= 2 and parts[0] == "GET" and parts[1].split("?")[0] == "/healthz":
            return 200, {"status": "ok", **self.stats()}
        return 404, {"error": "not found"}


def _response(status: int, body: dict[str, Any]) -> bytes:
    """Build a complete HTTP/1.1 response."""
    payload = json.dumps(body).encode("utf-8")
    head = (
        f"HTTP/1.1 {status} {REASONS[status]}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    return head.encode("ascii") + payload
