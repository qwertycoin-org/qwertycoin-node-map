from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


MAINNET_GENESIS_HASH = "4f95857586e2c66063c277370eda99cd75897d773af09f0c3cd1e22f7e87db39"


def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    if raw not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return raw == "true"


def _secret_file(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    path = Path(value)
    try:
        secret = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"unable to read {name}") from exc
    if not secret:
        raise ValueError(f"{name} is empty")
    return secret


def _normalize_base_path(raw: str) -> str:
    value = raw.strip()
    if not value or value == "/":
        return ""
    if not value.startswith("/"):
        value = f"/{value}"
    value = value.rstrip("/")
    if "//" in value or any(part in {".", ".."} for part in value.split("/")):
        raise ValueError("PUBLIC_BASE_PATH is invalid")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    rpc_base_url: str
    rpc_auth: str
    rpc_username: str | None = field(repr=False)
    rpc_password: str | None = field(repr=False)
    poll_interval_seconds: int
    stale_after_seconds: int
    geoip_db_path: Path
    geoip_auto_update: bool
    data_dir: Path
    http_host: str
    http_port: int
    public_base_path: str
    cors_allowed_origins: tuple[str, ...]
    expected_genesis_hash: str
    expected_core_version: str
    rpc_max_response_bytes: int
    geoip_max_download_bytes: int
    geoip_max_database_bytes: int

    @property
    def snapshot_path(self) -> Path:
        return self.data_dir / "snapshot-v1.json"

    @property
    def history_path(self) -> Path:
        return self.data_dir / f"peer-history-v1-{self.source_fingerprint[:16]}.sqlite3"

    @property
    def history_key_path(self) -> Path:
        return self.data_dir / "peer-history-hmac-key-v1"

    @property
    def source_fingerprint(self) -> str:
        parsed = urlsplit(self.rpc_base_url)
        safe_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
        identity = f"{safe_url}|mainnet|{self.expected_genesis_hash.lower()}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    @classmethod
    def from_env(cls) -> "Settings":
        rpc_base_url = os.getenv("QWC_RPC_BASE_URL", "").strip().rstrip("/")
        if not rpc_base_url:
            raise ValueError("QWC_RPC_BASE_URL is required")
        parsed = urlsplit(rpc_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("QWC_RPC_BASE_URL must be an http(s) URL")
        if parsed.username or parsed.password:
            raise ValueError("QWC_RPC_BASE_URL must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("QWC_RPC_BASE_URL must not contain a query or fragment")

        auth = os.getenv("QWC_RPC_AUTH", "none").strip().lower()
        if auth not in {"none", "digest"}:
            raise ValueError("QWC_RPC_AUTH must be none or digest")
        username = _secret_file("QWC_RPC_USERNAME_FILE")
        password = _secret_file("QWC_RPC_PASSWORD_FILE")
        if auth == "digest" and (not username or not password):
            raise ValueError("digest authentication requires both RPC secret files")
        if auth == "none" and (username or password):
            raise ValueError("RPC secret files require QWC_RPC_AUTH=digest")

        poll = _int_env("POLL_INTERVAL_SECONDS", 300, minimum=30, maximum=86400)
        stale = _int_env("STALE_AFTER_SECONDS", 900, minimum=60, maximum=604800)
        if stale <= poll:
            raise ValueError("STALE_AFTER_SECONDS must be greater than POLL_INTERVAL_SECONDS")

        origins = tuple(
            origin.strip()
            for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
            if origin.strip()
        )
        for origin in origins:
            origin_url = urlsplit(origin)
            if (
                origin_url.scheme not in {"http", "https"}
                or not origin_url.netloc
                or origin_url.path not in {"", "/"}
                or origin_url.query
                or origin_url.fragment
            ):
                raise ValueError("CORS_ALLOWED_ORIGINS contains an invalid origin")

        data_dir = Path(os.getenv("DATA_DIR", "/data"))
        geoip_db = Path(os.getenv("GEOIP_DB_PATH", str(data_dir / "geoip/dbip-city-lite.mmdb")))
        expected_genesis = os.getenv("QWC_EXPECTED_GENESIS_HASH", MAINNET_GENESIS_HASH).strip().lower()
        if len(expected_genesis) != 64 or any(c not in "0123456789abcdef" for c in expected_genesis):
            raise ValueError("QWC_EXPECTED_GENESIS_HASH must be a 64-character hexadecimal hash")

        return cls(
            rpc_base_url=rpc_base_url,
            rpc_auth=auth,
            rpc_username=username,
            rpc_password=password,
            poll_interval_seconds=poll,
            stale_after_seconds=stale,
            geoip_db_path=geoip_db,
            geoip_auto_update=_bool_env("GEOIP_AUTO_UPDATE", True),
            data_dir=data_dir,
            http_host=os.getenv("HTTP_HOST", "0.0.0.0").strip(),
            http_port=_int_env("HTTP_PORT", 8080, minimum=1, maximum=65535),
            public_base_path=_normalize_base_path(os.getenv("PUBLIC_BASE_PATH", "")),
            cors_allowed_origins=origins,
            expected_genesis_hash=expected_genesis,
            expected_core_version=os.getenv("QWC_EXPECTED_CORE_VERSION", "2.0.2-release").strip(),
            rpc_max_response_bytes=_int_env(
                "RPC_MAX_RESPONSE_BYTES", 5 * 1024 * 1024, minimum=1024, maximum=50 * 1024 * 1024
            ),
            geoip_max_download_bytes=_int_env(
                "GEOIP_MAX_DOWNLOAD_BYTES", 250 * 1024 * 1024, minimum=1024, maximum=1024 * 1024 * 1024
            ),
            geoip_max_database_bytes=_int_env(
                "GEOIP_MAX_DATABASE_BYTES", 1024 * 1024 * 1024, minimum=1024, maximum=2 * 1024 * 1024 * 1024
            ),
        )
