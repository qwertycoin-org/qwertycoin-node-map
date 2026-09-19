# API v1 contract

`GET /api/v1/map` returns a single internally consistent snapshot. It never contains IP addresses, peer IDs, source addresses, RPC URLs or credentials.

```json
{
  "schema_version": 1,
  "network": "mainnet",
  "scope": "single_observer",
  "collected_at": "2026-09-19T12:00:00Z",
  "last_attempt_at": "2026-09-19T12:00:00Z",
  "collector_status": "ok",
  "collector_error": null,
  "data_age_seconds": 4,
  "stale": false,
  "poll_interval_seconds": 300,
  "geoip": {"provider": "DB-IP City Lite", "edition": "2026-09", "update_status": "current", "last_update_error_at": null},
  "summary": {"observed_public_ips": 2, "represented_countries": 2, "unknown_country_ips": 0, "non_mappable_public_ips": 0, "anonymous_connections": 1, "excluded_connections": 3},
  "countries": [{"code": "DE", "name": "Germany", "count": 1, "share_percent": 50.0}],
  "markers": [{"country_code": "DE", "latitude": 51.2, "longitude": 10.4, "count": 1}]
}
```

## Types and invariants

- timestamps are UTC RFC 3339 strings or `null` where documented;
- `collector_status` is `starting`, `ok` or `error`;
- `scope` is always `single_observer` in schema 1;
- coordinates are rounded to one decimal place and are presentation estimates;
- the sum of all country counts equals `observed_public_ips`;
- the sum of all marker counts plus `non_mappable_public_ips` equals `observed_public_ips`;
- `represented_countries` excludes the synthetic `ZZ`/Unknown row;
- a valid empty RPC connection result is represented by zero metrics and empty arrays;
- an absent or invalid RPC connection field is an error, not a zero measurement.

Without any complete snapshot, the endpoint returns HTTP 503 with `error: "unavailable"` and unknown metrics as `null`. With an older valid snapshot, it returns HTTP 200 and sets `collector_status: "error"` or `stale: true` as applicable.

## Historical peer presence

`GET /api/v1/history?window=30d` returns distinct public peer IPs observed at least once in the selected period. Allowed windows are `30d` (default), `7d` and `24h`. Repeated observations of the same canonical IP are counted once. This remains an IP-based, single-observer view: one IP is not necessarily one node, and several nodes can share an IP.

```json
{
  "schema_version": 1,
  "network": "mainnet",
  "scope": "single_observer_history",
  "window": "30d",
  "window_seconds": 2592000,
  "window_started_at": "2026-08-20T12:00:00Z",
  "window_ended_at": "2026-09-19T12:00:00Z",
  "tracking_started_at": "2026-09-19T08:00:00Z",
  "first_observed_at": "2026-09-19T08:00:00Z",
  "last_observed_at": "2026-09-19T12:00:00Z",
  "last_collection_at": "2026-09-19T12:00:00Z",
  "data_age_seconds": 4,
  "coverage_seconds": 14400,
  "partial_window": true,
  "retention_days": 30,
  "collector_status": "ok",
  "collector_error": null,
  "stale": false,
  "poll_interval_seconds": 300,
  "geoip": {"provider": "DB-IP City Lite", "edition": "2026-09", "update_status": "current", "last_update_error_at": null},
  "summary": {"observed_public_ips": 3, "represented_countries": 2, "unknown_country_ips": 0, "non_mappable_public_ips": 1},
  "countries": [{"code": "DE", "name": "Germany", "count": 2, "share_percent": 66.7}],
  "markers": [{"country_code": "DE", "latitude": 51.2, "longitude": 10.4, "count": 2}]
}
```

History invariants match the live endpoint: country counts sum to `observed_public_ips`, and marker counts plus `non_mappable_public_ips` sum to the same value. `partial_window` is true until tracking has covered the entire requested period. A successful empty observation creates a real zero-valued history; before the first successful observation the endpoint returns HTTP 503.

The persistent store never contains raw IP strings. It stores an HMAC token derived with a local mode-`0600` random key, the first and last observation timestamps, country and rounded coordinates. Expired rows are deleted after 30 days. The API exposes only the aggregate result shown above, never tokens or per-peer timestamps.
