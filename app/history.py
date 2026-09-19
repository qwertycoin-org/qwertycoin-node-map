from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import stat
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .aggregate import LocatedPeer


RETENTION = timedelta(days=30)
WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": RETENTION}
KEY_BYTES = 32


def _iso_from_epoch(value: int) -> str:
    return datetime.fromtimestamp(value, UTC).isoformat().replace("+00:00", "Z")


def _secure_regular_file(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError(f"{path.name} must be a regular file with one hard link")
    if info.st_uid != os.getuid():
        raise ValueError(f"{path.name} must be owned by the application user")
    if info.st_mode & 0o077:
        raise ValueError(f"{path.name} must not grant group or other access")


def _read_or_create_key(path: Path, *, allow_create: bool) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileNotFoundError:
        raise ValueError(f"{path.name} is required for the existing peer history") from None
    except FileExistsError:
        _secure_regular_file(path)
    else:
        if not allow_create:
            os.close(descriptor)
            path.unlink(missing_ok=True)
            raise ValueError(f"{path.name} is required for the existing peer history")
        try:
            key = secrets.token_bytes(KEY_BYTES)
            if os.write(descriptor, key) != KEY_BYTES:
                raise OSError("short write while creating peer-history key")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _secure_regular_file(path)

    read_flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        read_flags |= os.O_NOFOLLOW
    descriptor = os.open(path, read_flags)
    try:
        key = os.read(descriptor, KEY_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(key) != KEY_BYTES:
        raise ValueError(f"{path.name} has an invalid length")
    return key


def _prepare_database_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        _secure_regular_file(path)
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    os.close(descriptor)
    _secure_regular_file(path)


class PeerHistoryStore:
    """Stores 30-day peer-IP presence using keyed, non-public identifiers only."""

    def __init__(self, path: Path, key_path: Path, source_fingerprint: str) -> None:
        self._path = path
        self._source_fingerprint = source_fingerprint
        database_exists = path.exists() or path.is_symlink()
        self._key = _read_or_create_key(key_path, allow_create=not database_exists)
        _prepare_database_file(path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS peers (
                        peer_token BLOB PRIMARY KEY,
                        first_seen_at INTEGER NOT NULL,
                        last_seen_at INTEGER NOT NULL,
                        country_code TEXT NOT NULL,
                        country_name TEXT NOT NULL,
                        latitude REAL,
                        longitude REAL,
                        CHECK(length(peer_token) = 32),
                        CHECK(length(country_code) = 2),
                        CHECK((latitude IS NULL AND longitude IS NULL) OR
                              (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180))
                    )
                    """
                )
                connection.execute("CREATE INDEX IF NOT EXISTS peers_last_seen ON peers(last_seen_at)")
                schema = connection.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
                source = connection.execute("SELECT value FROM meta WHERE key = 'source_fingerprint'").fetchone()
                if schema is None:
                    connection.execute("INSERT INTO meta(key, value) VALUES ('schema_version', '1')")
                elif schema["value"] != "1":
                    raise ValueError("peer history schema version is unsupported")
                if source is None:
                    connection.execute(
                        "INSERT INTO meta(key, value) VALUES ('source_fingerprint', ?)",
                        (self._source_fingerprint,),
                    )
                elif not hmac.compare_digest(source["value"], self._source_fingerprint):
                    raise ValueError("peer history belongs to a different RPC source")
        self._secure_sidecars()

    def _secure_sidecars(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{self._path}{suffix}")
            if candidate.exists():
                os.chmod(candidate, 0o600)

    def _token(self, address: str) -> bytes:
        message = f"{self._source_fingerprint}\0{address}".encode("ascii")
        return hmac.new(self._key, message, hashlib.sha256).digest()

    def record(self, peers: tuple[LocatedPeer, ...], collected_at: datetime) -> None:
        if collected_at.tzinfo is None:
            raise ValueError("collected_at must be timezone-aware")
        observed_at = int(collected_at.timestamp())
        retention_cutoff = observed_at - int(RETENTION.total_seconds())
        rows = [
            (
                self._token(peer.address),
                observed_at,
                observed_at,
                peer.country_code,
                peer.country_name[:128],
                peer.latitude,
                peer.longitude,
            )
            for peer in peers
        ]
        with closing(self._connect()) as connection:
            with connection:
                connection.executemany(
                    """
                    INSERT INTO peers(
                        peer_token, first_seen_at, last_seen_at, country_code, country_name, latitude, longitude
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(peer_token) DO UPDATE SET
                        first_seen_at = MIN(peers.first_seen_at, excluded.first_seen_at),
                        last_seen_at = MAX(peers.last_seen_at, excluded.last_seen_at),
                        country_code = excluded.country_code,
                        country_name = excluded.country_name,
                        latitude = excluded.latitude,
                        longitude = excluded.longitude
                    """,
                    rows,
                )
                connection.execute("DELETE FROM peers WHERE last_seen_at < ?", (retention_cutoff,))
                connection.execute(
                    "INSERT OR IGNORE INTO meta(key, value) VALUES ('tracking_started_at', ?)",
                    (str(observed_at),),
                )
                connection.execute(
                    """
                    INSERT INTO meta(key, value) VALUES ('last_collection_at', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (str(observed_at),),
                )
        self._secure_sidecars()

    def public_payload(self, window: str, now: datetime | None = None) -> dict[str, Any] | None:
        duration = WINDOWS.get(window)
        if duration is None:
            raise ValueError("unsupported history window")
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        now_epoch = int(now.timestamp())
        cutoff = now_epoch - int(duration.total_seconds())

        with closing(self._connect()) as connection:
            metadata = {
                row["key"]: row["value"]
                for row in connection.execute(
                    "SELECT key, value FROM meta WHERE key IN ('tracking_started_at', 'last_collection_at')"
                )
            }
            if "tracking_started_at" not in metadata or "last_collection_at" not in metadata:
                return None
            total = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM peers WHERE last_seen_at >= ?", (cutoff,)
                ).fetchone()["count"]
            )
            country_rows = connection.execute(
                """
                SELECT country_code AS code, MAX(country_name) AS name, COUNT(*) AS count
                FROM peers WHERE last_seen_at >= ?
                GROUP BY country_code ORDER BY count DESC, name ASC
                """,
                (cutoff,),
            ).fetchall()
            marker_rows = connection.execute(
                """
                SELECT country_code, latitude, longitude, COUNT(*) AS count
                FROM peers
                WHERE last_seen_at >= ? AND latitude IS NOT NULL AND longitude IS NOT NULL
                GROUP BY country_code, latitude, longitude
                ORDER BY count DESC, country_code ASC, latitude ASC, longitude ASC
                """,
                (cutoff,),
            ).fetchall()
            first_last = connection.execute(
                """
                SELECT MIN(first_seen_at) AS first_seen_at, MAX(last_seen_at) AS last_seen_at
                FROM peers WHERE last_seen_at >= ?
                """,
                (cutoff,),
            ).fetchone()

        countries = [
            {
                "code": row["code"],
                "name": row["name"],
                "count": row["count"],
                "share_percent": round(row["count"] * 100 / total, 1) if total else 0.0,
            }
            for row in country_rows
        ]
        markers = [dict(row) for row in marker_rows]
        mapped = sum(row["count"] for row in markers)
        tracking_started = int(metadata["tracking_started_at"])
        last_collection = int(metadata["last_collection_at"])
        if sum(row["count"] for row in countries) != total or mapped > total:
            raise RuntimeError("peer history aggregation invariant failed")
        return {
            "schema_version": 1,
            "network": "mainnet",
            "scope": "single_observer_history",
            "window": window,
            "window_seconds": int(duration.total_seconds()),
            "window_started_at": _iso_from_epoch(cutoff),
            "window_ended_at": _iso_from_epoch(now_epoch),
            "tracking_started_at": _iso_from_epoch(tracking_started),
            "first_observed_at": _iso_from_epoch(first_last["first_seen_at"]) if first_last["first_seen_at"] else None,
            "last_observed_at": _iso_from_epoch(first_last["last_seen_at"]) if first_last["last_seen_at"] else None,
            "last_collection_at": _iso_from_epoch(last_collection),
            "data_age_seconds": max(0, now_epoch - last_collection),
            "coverage_seconds": max(0, min(int(duration.total_seconds()), now_epoch - tracking_started)),
            "partial_window": tracking_started > cutoff,
            "retention_days": 30,
            "summary": {
                "observed_public_ips": total,
                "represented_countries": sum(1 for row in countries if row["code"] != "ZZ"),
                "unknown_country_ips": sum(row["count"] for row in countries if row["code"] == "ZZ"),
                "non_mappable_public_ips": total - mapped,
            },
            "countries": countries,
            "markers": markers,
        }
