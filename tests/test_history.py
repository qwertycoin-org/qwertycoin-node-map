from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.aggregate import LocatedPeer
from app.history import PeerHistoryStore


def peer(address, code, name, latitude=None, longitude=None):
    return LocatedPeer(address, code, name, latitude, longitude)


def test_history_deduplicates_filters_and_prunes_without_storing_raw_ips(tmp_path):
    database = tmp_path / "history.sqlite3"
    key = tmp_path / "history.key"
    store = PeerHistoryStore(database, key, "a" * 64)
    now = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

    store.record((peer("4.4.4.4", "FR", "France", 46.2, 2.2),), now - timedelta(days=31))
    store.record((peer("8.8.8.8", "US", "United States", 37.4, -122.1),), now - timedelta(days=20))
    store.record(
        (
            peer("8.8.8.8", "US", "United States", 37.4, -122.1),
            peer("1.1.1.1", "AU", "Australia", None, None),
        ),
        now - timedelta(days=5),
    )
    store.record((peer("9.9.9.9", "ZZ", "Unknown", None, None),), now - timedelta(hours=12))

    day = store.public_payload("24h", now)
    week = store.public_payload("7d", now)
    month = store.public_payload("30d", now)
    assert day["summary"]["observed_public_ips"] == 1
    assert week["summary"] == {
        "observed_public_ips": 3,
        "represented_countries": 2,
        "unknown_country_ips": 1,
        "non_mappable_public_ips": 2,
    }
    assert month["summary"]["observed_public_ips"] == 3
    assert sum(row["count"] for row in month["countries"]) == 3
    assert sum(row["count"] for row in month["markers"]) + month["summary"]["non_mappable_public_ips"] == 3
    assert {row["code"] for row in month["countries"]} == {"US", "AU", "ZZ"}
    assert month["partial_window"] is False
    assert key.stat().st_mode & 0o077 == 0
    assert database.stat().st_mode & 0o077 == 0
    for stored_file in tmp_path.iterdir():
        if stored_file.is_file() and stored_file != key:
            contents = stored_file.read_bytes()
            assert b"8.8.8.8" not in contents
            assert b"4.4.4.4" not in contents

    reopened = PeerHistoryStore(database, key, "a" * 64)
    assert reopened.public_payload("30d", now)["summary"]["observed_public_ips"] == 3


def test_empty_success_is_history_and_new_store_is_partial(tmp_path):
    now = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
    store = PeerHistoryStore(tmp_path / "history.sqlite3", tmp_path / "history.key", "b" * 64)
    assert store.public_payload("30d", now) is None
    store.record((), now)
    payload = store.public_payload("30d", now)
    assert payload["summary"]["observed_public_ips"] == 0
    assert payload["countries"] == []
    assert payload["markers"] == []
    assert payload["partial_window"] is True


def test_history_is_bound_to_source_and_rejects_unsafe_key_permissions(tmp_path):
    database = tmp_path / "history.sqlite3"
    key = tmp_path / "history.key"
    PeerHistoryStore(database, key, "c" * 64)
    with pytest.raises(ValueError, match="different RPC source"):
        PeerHistoryStore(database, key, "d" * 64)

    unsafe_key = tmp_path / "unsafe.key"
    unsafe_key.write_bytes(b"x" * 32)
    unsafe_key.chmod(0o640)
    with pytest.raises(ValueError, match="group or other"):
        PeerHistoryStore(tmp_path / "unsafe.sqlite3", unsafe_key, "e" * 64)

    missing_key_db = tmp_path / "missing-key.sqlite3"
    missing_key_db.touch(mode=0o600)
    with pytest.raises(ValueError, match="required for the existing"):
        PeerHistoryStore(missing_key_db, tmp_path / "missing.key", "e" * 64)


def test_history_rejects_unknown_window(tmp_path):
    store = PeerHistoryStore(tmp_path / "history.sqlite3", tmp_path / "history.key", "f" * 64)
    with pytest.raises(ValueError, match="unsupported"):
        store.public_payload("90d")
