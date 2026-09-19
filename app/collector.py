from __future__ import annotations

import asyncio
import copy
import logging
from datetime import UTC, datetime
from typing import Any

from .aggregate import aggregate_ips
from .config import Settings
from .geoip import GeoIpManager
from .peers import normalize_connections
from .rpc import QwcRpcClient
from .snapshot import SnapshotStore


LOGGER = logging.getLogger("qwertycoin_node_map.collector")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


class Collector:
    def __init__(
        self,
        settings: Settings,
        rpc: QwcRpcClient,
        geoip: GeoIpManager,
        store: SnapshotStore,
    ) -> None:
        self._settings = settings
        self._rpc = rpc
        self._geoip = geoip
        self._store = store
        self._snapshot = store.load()
        self._status = "starting"
        self._last_attempt_at: datetime | None = None
        self._last_error: str | None = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._run_lock = asyncio.Lock()

    @property
    def has_snapshot(self) -> bool:
        return self._snapshot is not None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run_loop(), name="node-map-collector")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            await self.collect_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._settings.poll_interval_seconds)
            except TimeoutError:
                continue

    async def collect_once(self) -> bool:
        if self._run_lock.locked():
            return False
        async with self._run_lock:
            attempted = _utc_now()
            self._last_attempt_at = attempted
            try:
                await asyncio.wait_for(self._geoip.ensure_ready(), timeout=30)
                source = await asyncio.wait_for(self._rpc.validate_source(self._settings), timeout=30)
                connections = await asyncio.wait_for(self._rpc.connections(), timeout=30)
                normalized = normalize_connections(connections)
                aggregated = aggregate_ips(normalized.public_ips, self._geoip)
                snapshot = {
                    "schema_version": 1,
                    "network": source["network"],
                    "scope": "single_observer",
                    "collected_at": _iso(_utc_now()),
                    "last_attempt_at": _iso(attempted),
                    "collector_status": "ok",
                    "data_age_seconds": 0,
                    "stale": False,
                    "poll_interval_seconds": self._settings.poll_interval_seconds,
                    "geoip": {
                        "provider": "DB-IP City Lite",
                        "edition": self._geoip.edition,
                        "update_status": self._geoip.update_status,
                        "last_update_error_at": self._geoip.last_update_error_at,
                    },
                    "summary": {
                        "observed_public_ips": aggregated.unique_public_ips,
                        "represented_countries": aggregated.country_count,
                        "unknown_country_ips": aggregated.unknown_country_ips,
                        "non_mappable_public_ips": aggregated.non_mappable_public_ips,
                        "anonymous_connections": normalized.anonymous_connections,
                        "excluded_connections": normalized.excluded_connections,
                    },
                    "countries": aggregated.countries,
                    "markers": aggregated.markers,
                }
                self._store.save(snapshot)
                self._snapshot = snapshot
                self._status = "ok"
                self._last_error = None
                LOGGER.info(
                    "collection succeeded: %d public IPs, %d countries, %d anonymous connections",
                    aggregated.unique_public_ips,
                    aggregated.country_count,
                    normalized.anonymous_connections,
                )
                return True
            except Exception as exc:
                self._status = "error"
                self._last_error = "The most recent collection attempt failed."
                LOGGER.warning("collection failed: %s", type(exc).__name__)
                return False

    def public_payload(self) -> dict[str, Any] | None:
        if self._snapshot is None:
            return None
        payload = copy.deepcopy(self._snapshot)
        collected = datetime.fromisoformat(str(payload["collected_at"]).replace("Z", "+00:00"))
        age = max(0, int((_utc_now() - collected).total_seconds()))
        payload["data_age_seconds"] = age
        payload["stale"] = age > self._settings.stale_after_seconds
        payload["collector_status"] = self._status
        if self._last_attempt_at is not None:
            payload["last_attempt_at"] = _iso(self._last_attempt_at)
        payload["collector_error"] = self._last_error
        payload["geoip"]["update_status"] = self._geoip.update_status
        payload["geoip"]["last_update_error_at"] = self._geoip.last_update_error_at
        return payload

    def unavailable_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "error": "unavailable",
            "message": "No complete node-map snapshot is available yet.",
            "network": "mainnet",
            "scope": "single_observer",
            "collected_at": None,
            "last_attempt_at": _iso(self._last_attempt_at) if self._last_attempt_at else None,
            "collector_status": self._status,
            "data_age_seconds": None,
            "stale": True,
            "poll_interval_seconds": self._settings.poll_interval_seconds,
            "summary": {
                "observed_public_ips": None,
                "represented_countries": None,
                "unknown_country_ips": None,
                "non_mappable_public_ips": None,
            },
        }

