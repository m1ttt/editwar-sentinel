"""DiffService and GET /api/diff, with httpx.MockTransport instead of Wikipedia."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from editwar_api.diffs import (
    NEW_PAGE_DETAIL,
    DiffService,
    InvalidRequestError,
    UpstreamError,
    is_allowed_server,
    parse_compare,
)

SERVER = "https://en.wikipedia.org"
BODY = '<tr><td class="diff-marker" data-marker="−"></td><td>old</td></tr>'
COMPARE = {
    "compare": {
        "fromid": 1,
        "fromrevid": 10,
        "fromuser": "Alice",
        "fromcomment": "add text",
        "fromsize": 120,
        "toid": 1,
        "torevid": 11,
        "touser": "Bob",
        "tocomment": "Undid revision 10 by Alice",
        "tosize": 100,
        "body": BODY,
    }
}
NO_SUCH_REVISION = {"error": {"code": "nosuchrevid", "info": "There is no revision with ID 11."}}

Handler = Callable[[httpx.Request], httpx.Response]


def service(handler: Handler, calls: list[httpx.Request], **options: int) -> DiffService:
    def record(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return DiffService(client=client, **options)


def answer(payload: object, status: int = 200) -> Handler:
    return lambda request: httpx.Response(status, json=payload)


@pytest.mark.parametrize(
    ("server_url", "allowed"),
    [
        ("https://en.wikipedia.org", True),
        ("https://es.m.wikipedia.org", True),
        ("https://commons.wikimedia.org", True),
        ("https://www.wikidata.org", True),
        ("https://www.mediawiki.org", True),
        ("https://zh-classical.wiktionary.org", True),
        ("http://en.wikipedia.org", False),
        ("https://en.wikipedia.org/", False),
        ("https://en.wikipedia.org.evil.com", False),
        ("https://evil.com/.wikipedia.org", False),
        ("https://en.wikipedia.org@evil.com", False),
        ("https://a.b.wikipedia.org", False),
        ("https://localhost", False),
        ("https://en.wikipedia.org\n", False),
        ("https://EN.wikipedia.org", False),
    ],
)
def test_allowed_servers(server_url: str, allowed: bool) -> None:
    assert is_allowed_server(server_url) is allowed


def test_parse_compare_rejects_unexpected_answers() -> None:
    with pytest.raises(UpstreamError):
        parse_compare(SERVER, 11, 10, [])
    with pytest.raises(UpstreamError):
        parse_compare(SERVER, 11, 10, {"compare": {"fromuser": "A"}})


async def test_diff_success_and_cache() -> None:
    calls: list[httpx.Request] = []
    diffs = service(answer(COMPARE), calls)
    first = await diffs.diff(SERVER, 11, 10)
    second = await diffs.diff(SERVER, 11, 10)
    assert first is second
    assert len(calls) == 1  # the second answer came from the cache
    request = calls[0]
    assert request.url.host == "en.wikipedia.org"
    assert request.url.path == "/w/api.php"
    assert dict(request.url.params) == {
        "action": "compare",
        "fromrev": "10",
        "torev": "11",
        "prop": "diff|user|comment|size",
        "format": "json",
        "formatversion": "2",
    }
    assert first.to_dict() == {
        "server_url": SERVER,
        "rev_id": 11,
        "old_rev_id": 10,
        "html": BODY,
        "from_user": "Alice",
        "to_user": "Bob",
        "comment": "Undid revision 10 by Alice",
        "diff_url": "https://en.wikipedia.org/w/index.php?diff=11&oldid=10",
    }
    await diffs.close()


async def test_cache_size_is_limited() -> None:
    calls: list[httpx.Request] = []
    diffs = service(answer(COMPARE), calls, cache_size=2)
    for rev_id in (11, 12, 13):
        await diffs.diff(SERVER, rev_id, 10)
    await diffs.diff(SERVER, 13, 10)  # still cached
    await diffs.diff(SERVER, 11, 10)  # evicted, asked again
    assert len(calls) == 4
    await diffs.close()


async def test_service_validates_before_any_request() -> None:
    calls: list[httpx.Request] = []
    diffs = service(answer(COMPARE), calls)
    with pytest.raises(InvalidRequestError):
        await diffs.diff("https://evil.example", 11, 10)
    with pytest.raises(InvalidRequestError):
        await diffs.diff(SERVER, 0, 10)
    assert calls == []
    await diffs.close()


async def test_errors_are_not_cached() -> None:
    calls: list[httpx.Request] = []
    diffs = service(answer({}, status=503), calls)
    for _ in range(2):
        with pytest.raises(UpstreamError):
            await diffs.diff(SERVER, 11, 10)
    assert len(calls) == 2
    await diffs.close()


# --- GET /api/diff -------------------------------------------------------------


async def use_service(client: httpx.AsyncClient, diffs: DiffService) -> None:
    app = client.app  # type: ignore[attr-defined]
    await app.state.diffs.close()
    app.state.diffs = diffs  # the lifespan closes it at the end of the test


async def test_endpoint_success(client: httpx.AsyncClient) -> None:
    calls: list[httpx.Request] = []
    await use_service(client, service(answer(COMPARE), calls))
    params = {"server_url": SERVER, "rev_id": 11, "old_rev_id": 10}
    response = await client.get("/api/diff", params=params)
    assert response.status_code == 200
    body = response.json()
    assert body["html"] == BODY
    assert body["from_user"] == "Alice" and body["to_user"] == "Bob"
    assert body["diff_url"] == "https://en.wikipedia.org/w/index.php?diff=11&oldid=10"
    assert set(body) == {
        "server_url",
        "rev_id",
        "old_rev_id",
        "html",
        "from_user",
        "to_user",
        "comment",
        "diff_url",
    }
    assert (await client.get("/api/diff", params=params)).json() == body
    assert len(calls) == 1


@pytest.mark.parametrize(
    "server_url",
    ["https://evil.example", "http://en.wikipedia.org", "https://169.254.169.254", "file:///etc"],
)
async def test_endpoint_rejects_other_hosts(client: httpx.AsyncClient, server_url: str) -> None:
    calls: list[httpx.Request] = []
    await use_service(client, service(answer(COMPARE), calls))
    params = {"server_url": server_url, "rev_id": 11, "old_rev_id": 10}
    response = await client.get("/api/diff", params=params)
    assert response.status_code == 400
    assert calls == []


async def test_endpoint_new_page(client: httpx.AsyncClient) -> None:
    calls: list[httpx.Request] = []
    await use_service(client, service(answer(COMPARE), calls))
    params = {"server_url": SERVER, "rev_id": 11, "old_rev_id": 0}
    response = await client.get("/api/diff", params=params)
    assert response.status_code == 422
    assert response.json()["detail"] == NEW_PAGE_DETAIL
    assert calls == []


@pytest.mark.parametrize(
    "params",
    [
        {"server_url": SERVER, "rev_id": 0, "old_rev_id": 10},
        {"server_url": SERVER, "rev_id": 11, "old_rev_id": -1},
        {"server_url": SERVER, "rev_id": "x", "old_rev_id": 10},
        {"rev_id": 11, "old_rev_id": 10},
    ],
)
async def test_endpoint_validates_parameters(
    client: httpx.AsyncClient, params: dict[str, object]
) -> None:
    response = await client.get("/api/diff", params=params)  # type: ignore[arg-type]
    assert response.status_code == 422


async def test_endpoint_upstream_error(client: httpx.AsyncClient) -> None:
    calls: list[httpx.Request] = []
    await use_service(client, service(answer({}, status=500), calls))
    params = {"server_url": SERVER, "rev_id": 11, "old_rev_id": 10}
    assert (await client.get("/api/diff", params=params)).status_code == 502


async def test_endpoint_upstream_timeout(client: httpx.AsyncClient) -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    await use_service(client, service(timeout, []))
    params = {"server_url": SERVER, "rev_id": 11, "old_rev_id": 10}
    assert (await client.get("/api/diff", params=params)).status_code == 502


async def test_endpoint_upstream_not_json(client: httpx.AsyncClient) -> None:
    await use_service(client, service(lambda request: httpx.Response(200, text="<html>"), []))
    params = {"server_url": SERVER, "rev_id": 11, "old_rev_id": 10}
    assert (await client.get("/api/diff", params=params)).status_code == 502


async def test_endpoint_mediawiki_error(client: httpx.AsyncClient) -> None:
    await use_service(client, service(answer(NO_SUCH_REVISION), []))
    params = {"server_url": SERVER, "rev_id": 11, "old_rev_id": 10}
    response = await client.get("/api/diff", params=params)
    assert response.status_code == 404
    assert response.json()["detail"].startswith("nosuchrevid")
