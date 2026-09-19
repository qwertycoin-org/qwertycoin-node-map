from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        rpc_base_url="http://qwc-daemon:8197",
        rpc_auth="none",
        rpc_username=None,
        rpc_password=None,
        poll_interval_seconds=300,
        stale_after_seconds=900,
        geoip_db_path=tmp_path / "geoip/test.mmdb",
        geoip_auto_update=False,
        data_dir=tmp_path,
        http_host="127.0.0.1",
        http_port=8080,
        public_base_path="",
        cors_allowed_origins=(),
        expected_genesis_hash="4f95857586e2c66063c277370eda99cd75897d773af09f0c3cd1e22f7e87db39",
        expected_core_version="2.0.2-release",
        rpc_max_response_bytes=5 * 1024 * 1024,
        geoip_max_download_bytes=250 * 1024 * 1024,
        geoip_max_database_bytes=1024 * 1024 * 1024,
    )
