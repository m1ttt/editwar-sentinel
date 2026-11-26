"""Record raw events from the Wikimedia recentchange stream into a JSONL file.

Usage (from the repo root):

    uv run python services/ingestor/scripts/record_fixture.py --count 3000 --out data/replay.jsonl

Each line of the output file is one raw recentchange event, exactly as the
stream sends it, minus a few large fields that the ingestor never reads.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
from httpx_sse import aconnect_sse

STREAM_URL = "https://stream.wikimedia.org/v2/stream/recentchange"
USER_AGENT = "EditWarSentinel/0.1 (student project; https://github.com/m1ttt/editwar-sentinel)"

# Fields that can be large and that EventNormalizer does not use.
DROPPED_FIELDS = ("log_params", "parsedcomment")


def slim(event: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the event without the large unused fields."""
    return {key: value for key, value in event.items() if key not in DROPPED_FIELDS}


async def record(count: int, out: Path, url: str) -> int:
    """Read `count` events from the stream and write them to `out`. Returns the count written."""
    written = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/event-stream"}
    timeout = httpx.Timeout(30.0, read=60.0)
    async with (
        httpx.AsyncClient(headers=headers, timeout=timeout) as client,
        aconnect_sse(client, "GET", url) as event_source,
    ):
        event_source.response.raise_for_status()
        with out.open("w", encoding="utf-8") as handle:
            async for sse in event_source.aiter_sse():
                if sse.event != "message" or not sse.data:
                    continue
                event = json.loads(sse.data)
                # Wikimedia sends synthetic "canary" events to monitor the stream.
                if event.get("meta", {}).get("domain") == "canary":
                    continue
                handle.write(json.dumps(slim(event), ensure_ascii=False) + "\n")
                written += 1
                if written % 500 == 0:
                    print(f"recorded {written} events")
                if written >= count:
                    break
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=3000, help="number of events to record")
    parser.add_argument("--out", type=Path, required=True, help="output JSONL file")
    parser.add_argument("--url", default=STREAM_URL, help="stream URL")
    args = parser.parse_args()
    written = asyncio.run(record(args.count, args.out, args.url))
    print(f"wrote {written} events to {args.out}")


if __name__ == "__main__":
    main()
