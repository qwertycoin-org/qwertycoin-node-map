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
