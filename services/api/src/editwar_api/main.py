"""Entry point of the `editwar-api` command (see pyproject.toml)."""

from __future__ import annotations

import uvicorn

from editwar_api.app import create_app
from editwar_api.config import Settings


def main() -> None:
    """Run the api with uvicorn on 0.0.0.0:PORT (default 8000)."""
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
