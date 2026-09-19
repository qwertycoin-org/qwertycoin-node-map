from app.snapshot import SnapshotStore


def test_snapshot_is_atomic_and_bound_to_source(tmp_path):
    path = tmp_path / "snapshot.json"
    payload = {"schema_version": 1, "network": "mainnet"}
    SnapshotStore(path, "source-a").save(payload)
    assert SnapshotStore(path, "source-a").load() == payload
    assert SnapshotStore(path, "source-b").load() is None
    assert oct(path.stat().st_mode & 0o777) == "0o600"
