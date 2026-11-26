"""WikimediaSSESource against a fake SSE server (httpx.MockTransport)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from editwar_ingestor.sources import USER_AGENT, WikimediaSSESource

URL = "https://stream.example.org/v2/stream/recentchange"


def sse_body(*events: tuple[str, dict[str, Any]]) -> bytes:
    """Build an SSE body. Each event is (sse id, payload)."""
    chunks = []
    for event_id, payload in events:
        chunks.append(f"event: message\nid: {event_id}\ndata: {json.dumps(payload)}\n\n")
    return "".join(chunks).encode("utf-8")


def sse_response(body: bytes) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)


class FakeServer:
    """Answer each request with the next prepared response and record the requests."""

    def __init__(self, responses: list[Callable[[], httpx.Response]]) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.responses) - 1)
        return self.responses[index]()


class FakeSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def make_source(server: FakeServer, sleep: FakeSleep, **kwargs: Any) -> WikimediaSSESource:
    return WikimediaSSESource(URL, transport=httpx.MockTransport(server), sleep=sleep, **kwargs)


async def take(source: WikimediaSSESource, count: int) -> list[dict[str, Any]]:
    events = []
    stream = source.events()
    async for event in stream:
        events.append(event)
        if len(events) == count:
            break
    await stream.aclose()  # type: ignore[attr-defined]
    await source.close()
    return events


async def test_reads_events_and_sends_user_agent() -> None:
    server = FakeServer([lambda: sse_response(sse_body(("a", {"n": 1}), ("b", {"n": 2})))])
    sleep = FakeSleep()
    source = make_source(server, sleep)
    events = await take(source, 2)
    assert events == [{"n": 1}, {"n": 2}]
    request = server.requests[0]
    assert request.headers["User-Agent"] == USER_AGENT
    assert request.headers["Accept"] == "text/event-stream"
    assert "Last-Event-ID" not in request.headers
    assert source.last_event_id == "b"
    assert sleep.calls == []


async def test_reconnects_with_last_event_id_and_backoff() -> None:
    server = FakeServer(
        [
            lambda: sse_response(sse_body(("id-1", {"n": 1}), ("id-2", {"n": 2}))),  # then ends
            lambda: httpx.Response(500),
            lambda: httpx.Response(503),
            lambda: sse_response(sse_body(("id-3", {"n": 3}))),
        ]
    )
    sleep = FakeSleep()
    source = make_source(server, sleep)
    events = await take(source, 3)
    assert events == [{"n": 1}, {"n": 2}, {"n": 3}]
    # End of stream waits 1 s, the two errors wait 2 s and 4 s.
    assert sleep.calls == [1.0, 2.0, 4.0]
    assert source.reconnects == 3
    assert [r.headers.get("Last-Event-ID") for r in server.requests] == [
        None,
        "id-2",
        "id-2",
        "id-2",
    ]
    # A good event resets the backoff.
    assert source.backoff == 1.0


async def test_backoff_is_capped() -> None:
    failures: list[Callable[[], httpx.Response]] = [lambda: httpx.Response(503)] * 8
    server = FakeServer([*failures, lambda: sse_response(sse_body(("x", {"n": 1})))])
    sleep = FakeSleep()
    source = make_source(server, sleep, max_backoff=30.0)
    await take(source, 1)
    assert sleep.calls == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0]


async def test_network_error_triggers_reconnect() -> None:
    calls = {"count": 0}

    def flaky() -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ConnectError("connection refused")
        return sse_response(sse_body(("ok", {"n": 1})))

    server = FakeServer([flaky])
    sleep = FakeSleep()
    events = await take(make_source(server, sleep), 1)
    assert events == [{"n": 1}]
    assert sleep.calls == [1.0]


async def test_wrong_content_type_triggers_reconnect() -> None:
    server = FakeServer(
        [
            lambda: httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html>"),
            lambda: sse_response(sse_body(("ok", {"n": 1}))),
        ]
    )
    sleep = FakeSleep()
    events = await take(make_source(server, sleep), 1)
    assert events == [{"n": 1}]
    assert sleep.calls == [1.0]


async def test_skips_non_message_and_bad_json() -> None:
    body = (
        b": heartbeat comment\n\n"
        b"event: other\ndata: {}\n\n"
        b"event: message\nid: 1\ndata: not json\n\n"
        b"event: message\nid: 2\ndata:\n\n"
        b'event: message\nid: 3\ndata: {"n": 3}\n\n'
    )
    server = FakeServer([lambda: sse_response(body)])
    source = make_source(server, FakeSleep())
    events = await take(source, 1)
    assert events == [{"n": 3}]
    assert source.last_event_id == "3"


async def test_starts_from_given_last_event_id() -> None:
    server = FakeServer([lambda: sse_response(sse_body(("next", {"n": 1})))])
    source = make_source(server, FakeSleep(), last_event_id="resume-here")
    await take(source, 1)
    assert server.requests[0].headers["Last-Event-ID"] == "resume-here"


async def test_connect_and_close_are_idempotent() -> None:
    source = WikimediaSSESource(URL)
    await source.connect()
    await source.connect()
    await source.close()
    await source.close()
