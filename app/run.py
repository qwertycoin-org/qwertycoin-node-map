from __future__ import annotations

import uvicorn

from .config import Settings


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=settings.http_host,
        port=settings.http_port,
        workers=1,
        access_log=False,
    )


if __name__ == "__main__":
    main()
