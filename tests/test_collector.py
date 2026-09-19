from __future__ import annotations

import pytest

from app.collector import Collector
from app.snapshot import SnapshotStore


class FakeRpc:
    fail = False

    async def validate_source(self, settings):
        if self.fail:
            raise RuntimeError("synthetic failure")
        return {"network": "mainnet", "core_version": "2.0.2-release"}

    async def connections(self):
        return [
            {"host": "8.8.8.8", "state": "normal", "peer_id": "1", "address_type": "IPv4"},
            {"host": "8.8.8.8", "state": "normal", "peer_id": "2", "address_type": "IPv4"},
        ]


class FakeGeoIp:
    edition = "2099-01"
    update_status = "current"
    last_update_error_at = None

    async def ensure_ready(self):
        return None

    def lookup(self, address):
        return {
            "country": {"iso_code": "US", "names": {"en": "United States"}},
            "location": {"latitude": 37.4, "longitude": -122.1},
        }


@pytest.mark.asyncio
async def test_failure_preserves_last_successful_snapshot(settings):
    rpc = FakeRpc()
    collector = Collector(settings, rpc, FakeGeoIp(), SnapshotStore(settings.snapshot_path, settings.source_fingerprint))
    assert await collector.collect_once() is True
    first = collector.public_payload()
    assert first["summary"]["observed_public_ips"] == 1
    collected_at = first["collected_at"]

    rpc.fail = True
    assert await collector.collect_once() is False
    failed = collector.public_payload()
    assert failed["collected_at"] == collected_at
    assert failed["summary"]["observed_public_ips"] == 1
    assert failed["collector_status"] == "error"
    assert "synthetic" not in failed["collector_error"]
