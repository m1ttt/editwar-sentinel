"""WebSocketHub: sends live messages to every connected dashboard.

Every message is JSON: {"type": "edit" | "revert" | "alert" | "stats", "data": {...}}.
Wikipedia has dozens of edits per second, so edit messages are sampled: at
most `edits_per_second` edit messages leave the hub each second. Reverts,
alerts and stats always go through.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

logger = logging.getLogger("editwar.api")


class Connection(Protocol):
    """The part of starlette's WebSocket that the hub uses. Tests use fakes."""

    async def accept(self) -> None: ...

    async def send_text(self, data: str) -> None: ...


class WebSocketHub:
    def __init__(
        self,
        edits_per_second: int = 15,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._connections: set[Connection] = set()
        self._edits_per_second = edits_per_second
        self._clock = clock
        self._current_second = -1
        self._edits_this_second = 0

    def connection_count(self) -> int:
        return len(self._connections)

    async def connect(self, websocket: Connection) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: Connection) -> None:
        self._connections.discard(websocket)

    async def _send(self, websocket: Connection, text: str) -> None:
        """Send to one client. A client that fails is removed."""
        try:
            await websocket.send_text(text)
        except Exception:
            logger.info("websocket client removed after a failed send")
            self.disconnect(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send one message to all the clients at the same time."""
        if not self._connections:
            return
        text = json.dumps(message, ensure_ascii=False, default=str)
        await asyncio.gather(*(self._send(ws, text) for ws in list(self._connections)))

    def _edit_allowed(self) -> bool:
        """True while fewer than edits_per_second edits were sent in this second."""
        second = int(self._clock())
        if second != self._current_second:
            self._current_second = second
            self._edits_this_second = 0
        if self._edits_this_second >= self._edits_per_second:
            return False
        self._edits_this_second += 1
        return True

    async def broadcast_edit(self, data: dict[str, Any]) -> bool:
        """Send an "edit" message if the sample limit allows it. Returns True if sent."""
        if not self._connections or not self._edit_allowed():
            return False
        await self.broadcast({"type": "edit", "data": data})
        return True
