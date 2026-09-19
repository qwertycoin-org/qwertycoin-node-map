from pathlib import Path

import pytest

from app.config import Settings


def test_rejects_embedded_credentials(monkeypatch):
    monkeypatch.setenv("QWC_RPC_BASE_URL", "http://user:password@daemon:8197")
    with pytest.raises(ValueError, match="must not contain credentials"):
        Settings.from_env()


def test_rejects_stale_threshold_not_greater_than_poll(monkeypatch):
    monkeypatch.setenv("QWC_RPC_BASE_URL", "http://daemon:8197")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "300")
    monkeypatch.setenv("STALE_AFTER_SECONDS", "300")
    with pytest.raises(ValueError, match="must be greater"):
        Settings.from_env()


def test_normalizes_subpath_and_source_fingerprint(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("QWC_RPC_BASE_URL", "http://daemon:8197/")
    monkeypatch.setenv("PUBLIC_BASE_PATH", "node-map/")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings.from_env()
    assert settings.public_base_path == "/node-map"
    assert len(settings.source_fingerprint) == 64
    assert "daemon" not in settings.source_fingerprint
