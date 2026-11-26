"""Text diffs of one revision, for the edit-war timeline of the dashboard.

The dashboard cannot call the Wikipedia API itself (CORS and politeness), so
the api asks for it:

    GET {server_url}/w/api.php?action=compare&fromrev=<old>&torev=<new>&prop=diff|user|comment|size

`server_url` comes from the client, so it is checked against the Wikimedia
hosts before any request (no SSRF). A diff between two revisions never changes,
so successful answers stay in an LRU cache.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import OrderedDict
from dataclasses import asdict, dataclass
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request

from editwar_api.geo import USER_AGENT

logger = logging.getLogger("editwar.api")

# https://<lang or project>[.m].<wikimedia project>.org, nothing else.
ALLOWED_SERVER = re.compile(
    r"https://[a-z0-9-]+(\.m)?\.(wikipedia|wikimedia|wikidata|wiktionary|wikiquote|wikibooks"
    r"|wikisource|wikinews|wikiversity|wikivoyage|mediawiki)\.org"
)
NEW_PAGE_DETAIL = "new page, no previous revision"


class DiffError(Exception):
    """A diff that cannot be returned. `status_code` is the HTTP answer of the api."""

    status_code = 500

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class InvalidRequestError(DiffError):
    status_code = 400


class NewPageError(DiffError):
    status_code = 422


class RevisionNotFoundError(DiffError):
    """MediaWiki answered with an "error" object, for example nosuchrevid."""

    status_code = 404


class UpstreamError(DiffError):
    """The Wikipedia API did not answer, timed out or sent something unexpected."""

    status_code = 502


@dataclass(frozen=True, slots=True)
class Diff:
    """The changes of one revision, in the shape of GET /api/diff."""

    server_url: str
    rev_id: int
    old_rev_id: int
    html: str  # the <tr> rows of the MediaWiki diff table, without the <table>
    from_user: str | None
    to_user: str | None
    comment: str | None
    diff_url: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_allowed_server(server_url: str) -> bool:
    return ALLOWED_SERVER.fullmatch(server_url) is not None


def diff_url(server_url: str, rev_id: int, old_rev_id: int) -> str:
    return f"{server_url}/w/index.php?diff={rev_id}&oldid={old_rev_id}"


def parse_compare(server_url: str, rev_id: int, old_rev_id: int, payload: Any) -> Diff:
    """Build a Diff from an action=compare answer (formatversion=2)."""
    if not isinstance(payload, dict):
        raise UpstreamError("unexpected answer from the Wikipedia API")
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code", "error")
        raise RevisionNotFoundError(f"{code}: {error.get('info', 'revision not found')}")
    compare = payload.get("compare")
    if not isinstance(compare, dict) or not isinstance(compare.get("body"), str):
        raise UpstreamError("the Wikipedia API sent no diff")
    return Diff(
        server_url=server_url,
        rev_id=rev_id,
        old_rev_id=old_rev_id,
        html=compare["body"],
        from_user=compare.get("fromuser"),
        to_user=compare.get("touser"),
        comment=compare.get("tocomment"),
        diff_url=diff_url(server_url, rev_id, old_rev_id),
    )


class DiffService:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        cache_size: int = 256,
        concurrency: int = 4,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=5.0, headers={"User-Agent": USER_AGENT})
        self._cache: OrderedDict[tuple[str, int, int], Diff] = OrderedDict()
        self._cache_size = cache_size
        self._limit = asyncio.Semaphore(concurrency)  # polite to the Wikipedia API

    async def diff(self, server_url: str, rev_id: int, old_rev_id: int) -> Diff:
        """The diff from `old_rev_id` to `rev_id`. Raises a DiffError subclass."""
        if not is_allowed_server(server_url):
            raise InvalidRequestError("server_url must be a Wikimedia https host")
        if rev_id <= 0 or old_rev_id < 0:
            raise InvalidRequestError("rev_id must be > 0 and old_rev_id >= 0")
        if old_rev_id == 0:
            raise NewPageError(NEW_PAGE_DETAIL)
        key = (server_url, old_rev_id, rev_id)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        params = {
            "action": "compare",
            "fromrev": str(old_rev_id),
            "torev": str(rev_id),
            "prop": "diff|user|comment|size",
            "format": "json",
            "formatversion": "2",
        }
        async with self._limit:
            try:
                response = await self._client.get(f"{server_url}/w/api.php", params=params)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as error:
                logger.warning("diff %s %d..%d failed: %s", server_url, old_rev_id, rev_id, error)
                raise UpstreamError("the Wikipedia API did not answer") from error
        result = parse_compare(server_url, rev_id, old_rev_id, payload)
        self._cache[key] = result
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return result

    async def close(self) -> None:
        await self._client.aclose()


def diff_router() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["diffs"])

    @router.get("/diff")
    async def get_diff(
        request: Request,
        server_url: str,
        rev_id: int = Query(gt=0),
        old_rev_id: int = Query(ge=0),
    ) -> dict[str, Any]:
        """Diff of one revision against the previous one, as MediaWiki table rows."""
        diffs: DiffService = request.app.state.diffs
        try:
            found = await diffs.diff(server_url, rev_id, old_rev_id)
        except DiffError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail) from error
        return found.to_dict()

    return router
