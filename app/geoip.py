from __future__ import annotations

import asyncio
import gzip
import json
import os
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import maxminddb

from .config import Settings


class GeoIpError(RuntimeError):
    """A non-sensitive GeoIP lifecycle failure."""


class GeoIpManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._path = settings.geoip_db_path
        self._metadata_path = self._path.with_suffix(".json")
        self._reader: maxminddb.Reader | None = None
        self._reader_lock = threading.RLock()
        self._update_lock = asyncio.Lock()
        self._metadata: dict[str, Any] = {}
        self.update_status = "not_checked"
        self.last_update_error_at: str | None = None

    @property
    def edition(self) -> str:
        return str(self._metadata.get("edition", "provided"))

    def _load_metadata(self) -> None:
        try:
            payload = json.loads(self._metadata_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                self._metadata = payload
        except (OSError, json.JSONDecodeError):
            self._metadata = {}

    def open_existing(self) -> bool:
        self._load_metadata()
        if not self._path.is_file():
            return False
        try:
            reader = maxminddb.open_database(str(self._path))
            reader.metadata()
        except Exception as exc:
            raise GeoIpError("configured GeoIP database is invalid") from exc
        with self._reader_lock:
            old = self._reader
            self._reader = reader
            if old is not None:
                old.close()
        if not self._metadata:
            self._metadata = {"edition": "provided", "last_checked_at": None}
        return True

    def lookup(self, address: str) -> dict | None:
        with self._reader_lock:
            if self._reader is None:
                raise GeoIpError("GeoIP database is unavailable")
            result = self._reader.get(address)
            return result if isinstance(result, dict) else None

    def close(self) -> None:
        with self._reader_lock:
            if self._reader is not None:
                self._reader.close()
                self._reader = None

    def _last_check_recent(self, now: datetime) -> bool:
        raw = self._metadata.get("last_checked_at")
        if not isinstance(raw, str):
            return False
        try:
            checked = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return False
        return now - checked < timedelta(hours=24)

    async def ensure_ready(self, *, force_check: bool = False) -> None:
        async with self._update_lock:
            now = datetime.now(UTC)
            existing = False
            try:
                existing = self.open_existing()
            except GeoIpError:
                if not self._settings.geoip_auto_update:
                    raise
            if not self._settings.geoip_auto_update:
                if not existing:
                    raise GeoIpError("GeoIP database is missing and automatic updates are disabled")
                self.update_status = "disabled"
                return
            if existing and not force_check and self._last_check_recent(now):
                self.update_status = "current"
                return
            try:
                changed = await self._download_current(now)
                self.update_status = "updated" if changed else "current"
                self.last_update_error_at = None
            except Exception as exc:
                self.update_status = "error"
                self.last_update_error_at = now.isoformat().replace("+00:00", "Z")
                if not existing:
                    if isinstance(exc, GeoIpError):
                        raise
                    raise GeoIpError("unable to obtain a valid GeoIP database") from exc

    async def _download_current(self, now: datetime) -> bool:
        months = [now.replace(day=1)]
        months.append((months[0] - timedelta(days=1)).replace(day=1))
        current_edition = str(self._metadata.get("edition", ""))
        last_error: Exception | None = None
        for month in months:
            edition = month.strftime("%Y-%m")
            if current_edition == edition and self._path.is_file():
                self._write_metadata(edition, now)
                return False
            url = f"https://download.db-ip.com/free/dbip-city-lite-{edition}.mmdb.gz"
            try:
                await self._download_and_install(url, edition)
                self._write_metadata(edition, now)
                return True
            except GeoIpError as exc:
                last_error = exc
        raise GeoIpError("no valid current DB-IP City Lite edition was available") from last_error

    async def _download_and_install(self, url: str, edition: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        compressed_fd, compressed_name = tempfile.mkstemp(prefix="dbip-", suffix=".mmdb.gz", dir=self._path.parent)
        os.close(compressed_fd)
        database_fd, database_name = tempfile.mkstemp(prefix="dbip-", suffix=".mmdb", dir=self._path.parent)
        os.close(database_fd)
        compressed = Path(compressed_name)
        database = Path(database_name)
        try:
            timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
                async with client.stream("GET", url, headers={"User-Agent": "qwertycoin-node-map/1"}) as response:
                    if response.status_code != 200:
                        raise GeoIpError(f"GeoIP provider returned HTTP {response.status_code}")
                    size = 0
                    with compressed.open("wb") as output:
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > self._settings.geoip_max_download_bytes:
                                raise GeoIpError("GeoIP download exceeded the configured size limit")
                            output.write(chunk)
            await asyncio.to_thread(self._decompress_bounded, compressed, database)
            reader = await asyncio.to_thread(maxminddb.open_database, str(database))
            try:
                metadata = reader.metadata()
                if metadata.ip_version not in {4, 6} or metadata.node_count <= 0:
                    raise GeoIpError("downloaded GeoIP database metadata was invalid")
            finally:
                reader.close()
            os.chmod(database, 0o644)
            os.replace(database, self._path)
            self.open_existing()
            self._cleanup_old_files()
        except (OSError, gzip.BadGzipFile, EOFError) as exc:
            raise GeoIpError("downloaded GeoIP database could not be installed") from exc
        finally:
            compressed.unlink(missing_ok=True)
            database.unlink(missing_ok=True)

    def _decompress_bounded(self, source: Path, target: Path) -> None:
        written = 0
        with gzip.open(source, "rb") as input_file, target.open("wb") as output_file:
            while chunk := input_file.read(1024 * 1024):
                written += len(chunk)
                if written > self._settings.geoip_max_database_bytes:
                    raise GeoIpError("GeoIP database exceeded the configured size limit")
                output_file.write(chunk)

    def _write_metadata(self, edition: str, now: datetime) -> None:
        metadata = {
            "provider": "DB-IP City Lite",
            "edition": edition,
            "last_checked_at": now.isoformat().replace("+00:00", "Z"),
        }
        self._metadata_path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="geoip-meta-", suffix=".json", dir=self._metadata_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(metadata, output, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.chmod(name, 0o644)
            os.replace(name, self._metadata_path)
            self._metadata = metadata
        finally:
            Path(name).unlink(missing_ok=True)

    def _cleanup_old_files(self) -> None:
        candidates = sorted(self._path.parent.glob("dbip-*.mmdb*"), key=lambda path: path.stat().st_mtime, reverse=True)
        for candidate in candidates[4:]:
            candidate.unlink(missing_ok=True)
