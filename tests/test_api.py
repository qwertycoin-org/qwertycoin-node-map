from dataclasses import replace
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.aggregate import LocatedPeer
from app.main import create_app


def snapshot():
    return {
        "schema_version": 1,
        "network": "mainnet",
        "scope": "single_observer",
        "collected_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "last_attempt_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "collector_status": "ok",
        "data_age_seconds": 0,
        "stale": False,
        "poll_interval_seconds": 300,
        "geoip": {"provider": "DB-IP City Lite", "edition": "2099-01", "update_status": "current", "last_update_error_at": None},
        "summary": {"observed_public_ips": 1, "represented_countries": 1, "unknown_country_ips": 0, "non_mappable_public_ips": 0, "anonymous_connections": 0, "excluded_connections": 0},
        "countries": [{"code": "US", "name": "United States", "count": 1, "share_percent": 100.0}],
        "markers": [{"country_code": "US", "latitude": 37.4, "longitude": -122.1, "count": 1}],
    }


def test_unavailable_contract_and_security_headers(settings):
    app = create_app(settings)
    response = TestClient(app).get("/api/v1/map")
    assert response.status_code == 503
    assert response.json()["summary"]["observed_public_ips"] is None
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"].startswith("public")
    history = TestClient(app).get("/api/v1/history")
    assert history.status_code == 503
    assert history.json()["window"] == "30d"


def test_root_api_ready_and_static_assets(settings):
    app = create_app(settings)
    app.state.collector._snapshot = snapshot()
    app.state.collector._status = "ok"
    client = TestClient(app)
    root = client.get("/")
    assert root.status_code == 200
    assert 'class="site-header"' in root.text
    assert 'href="https://qwertycoin.org/#technology"' in root.text
    assert '<span class="brand-lockup"><strong>Qwertycoin</strong><span>Node Map</span></span>' in root.text
    assert 'data-history-window="30d"' in root.text
    assert 'data-history-window="7d"' in root.text
    assert 'data-history-window="24h"' in root.text
    assert 'page.js?v=qwc-history-1' in root.text
    assert 'data-theme-toggle' in root.text
    assert 'content="light dark"' in root.text
    assert client.head("/").status_code == 200
    api = client.get("/api/v1/map")
    assert api.status_code == 200
    assert client.head("/api/v1/map").status_code == 200
    assert api.json()["summary"]["observed_public_ips"] == 1
    assert client.get("/readyz").status_code == 200
    assert client.head("/readyz").status_code == 200
    assert client.get("/assets/node-map.js").status_code == 200
    assert "api/v1/history" in client.get("/assets/page.js").text


def test_history_api_defaults_to_30_days_and_validates_windows(settings):
    app = create_app(settings)
    now = datetime.now(UTC)
    app.state.history.record(
        (LocatedPeer("8.8.8.8", "US", "United States", 37.4, -122.1),),
        now,
    )
    app.state.collector._status = "ok"
    client = TestClient(app)
    default = client.get("/api/v1/history")
    assert default.status_code == 200
    assert default.json()["window"] == "30d"
    assert default.json()["scope"] == "single_observer_history"
    assert default.json()["summary"]["observed_public_ips"] == 1
    assert client.head("/api/v1/history?window=7d").status_code == 200
    assert client.get("/api/v1/history?window=24h").json()["window"] == "24h"
    assert client.get("/api/v1/history?window=90d").status_code == 422


def test_subpath_routes_and_redirect(settings):
    app = create_app(replace(settings, public_base_path="/node-map"))
    app.state.collector._snapshot = snapshot()
    app.state.collector._status = "ok"
    client = TestClient(app)
    redirect = client.get("/node-map", follow_redirects=False)
    assert redirect.status_code == 308
    assert redirect.headers["location"] == "/node-map/"
    assert client.get("/node-map/").status_code == 200
    assert client.get("/node-map/api/v1/map").status_code == 200
    assert client.get("/node-map/api/v1/history").status_code == 503
    assert client.get("/node-map/assets/node-map.css").status_code == 200
