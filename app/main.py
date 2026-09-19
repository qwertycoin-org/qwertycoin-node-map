from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .collector import Collector
from .config import Settings
from .geoip import GeoIpManager
from .rpc import QwcRpcClient
from .snapshot import SnapshotStore


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    rpc = QwcRpcClient(settings)
    geoip = GeoIpManager(settings)
    store = SnapshotStore(settings.snapshot_path, settings.source_fingerprint)
    collector = Collector(settings, rpc, geoip, store)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await collector.start()
        try:
            yield
        finally:
            await collector.stop()
            await rpc.close()
            geoip.close()

    app = FastAPI(
        title="Qwertycoin Node Map API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=f"{settings.public_base_path}/openapi.json",
        lifespan=lifespan,
    )
    app.state.collector = collector
    app.state.settings = settings

    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_allowed_origins),
            allow_credentials=False,
            allow_methods=["GET"],
            allow_headers=["Accept"],
            max_age=600,
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        )
        path = request.url.path
        if path.endswith(("/healthz", "/readyz")):
            response.headers["Cache-Control"] = "no-store"
        elif "/api/" in path:
            response.headers["Cache-Control"] = "public, max-age=15, stale-while-revalidate=15"
        elif "/assets/" in path:
            response.headers["Cache-Control"] = "public, max-age=86400"
        return response

    base = settings.public_base_path
    assets_path = f"{base}/assets" or "/assets"
    app.mount(assets_path, StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.api_route(f"{base}/api/v1/map", methods=["GET", "HEAD"], include_in_schema=True)
    async def map_api():
        payload = collector.public_payload()
        if payload is None:
            return JSONResponse(collector.unavailable_payload(), status_code=503)
        return JSONResponse(payload)

    @app.api_route(f"{base}/healthz", methods=["GET", "HEAD"], include_in_schema=False)
    async def healthz():
        return {"status": "ok"}

    @app.api_route(f"{base}/readyz", methods=["GET", "HEAD"], include_in_schema=False)
    async def readyz():
        payload = collector.public_payload()
        if payload is None or payload["stale"] or payload["collector_status"] != "ok":
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return {"status": "ready", "collected_at": payload["collected_at"]}

    @app.api_route(f"{base}/", methods=["GET", "HEAD"], include_in_schema=False)
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    if base:
        @app.api_route(base, methods=["GET", "HEAD"], include_in_schema=False)
        async def base_redirect():
            return RedirectResponse(f"{base}/", status_code=308)

    return app
