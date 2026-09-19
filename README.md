# Qwertycoin Node Map

A privacy-conscious world map of public peer IP origins observed by one Qwertycoin Mainnet node.

The service polls the unrestricted RPC of an **existing** Qwertycoin daemon, aggregates locations locally with DB-IP City Lite and serves only country/coordinate counts. It does not run a daemon, synchronize a blockchain, store raw peer addresses or expose the Core RPC to browsers.

> Based on connections observed by one Qwertycoin node. This is a partial network view. IP locations are approximate; one IP does not necessarily represent one node.

## Architecture

- one FastAPI/Uvicorn worker and one in-process background collector;
- `get_info`, genesis header and `get_connections` over an internal Core RPC path;
- local DB-IP City Lite MMDB with bounded monthly downloads and daily update checks;
- atomic aggregate-only JSON snapshots in `/data`;
- a 30-day SQLite history of keyed peer-presence tokens, countries and rounded coordinates; raw IPs are never persisted;
- Leaflet 1.9.4 and Natural Earth country boundaries served locally, without tiles or CDNs;
- root and configurable subpath operation for later Explorer integration.

In the live `/api/v1/map` snapshot, **Observed peer IPs** is the number of unique, globally routable IP addresses among handshake-complete connections in the latest successful collection. It is not a node census, an EPoSE metric or proof that a peer accepts inbound connections.

The public page defaults to the distinct public peer IPs observed during the last 30 days and can switch to 7 days or 24 hours. A peer seen in many five-minute collections is counted once per selected period. Internally, cross-collection deduplication uses an HMAC-SHA-256 token protected by a locally generated mode-`0600` key. Rows expire 30 days after their last observation; neither tokens nor individual first/last-seen records are exposed by the API.

## Quick start with an existing Docker daemon

1. Copy `.env.example` to `.env`.
2. Set `QWC_RPC_BASE_URL` to the daemon service name on its private Docker network.
3. Set `QWC_DOCKER_NETWORK` to that existing network.
4. Build and start:

```sh
docker compose build --pull
docker compose up -d
curl --fail http://127.0.0.1:18082/healthz
curl --fail http://127.0.0.1:18082/readyz
```

Only loopback port `18082` is published by default. Put the existing HTTPS reverse proxy in front of it. Do not publish the unrestricted QWC RPC.

The application refuses a source that is not Mainnet, has a different genesis hash or reports a different configured Core version.

## Host-network mode

If the existing daemon is a host process whose RPC listens only on `127.0.0.1`, use `compose.host-network.yaml`. Create `.env.host` with:

```dotenv
QWC_RPC_BASE_URL=http://127.0.0.1:8197
QWC_RPC_AUTH=none
HTTP_HOST=127.0.0.1
HTTP_PORT=8080
GEOIP_AUTO_UPDATE=true
```

Host networking deliberately has no `ports` mapping. The application HTTP listener remains explicitly bound to loopback.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `QWC_RPC_BASE_URL` | required | Internal Core base URL without `/json_rpc` or embedded credentials |
| `QWC_RPC_AUTH` | `none` | `none` or `digest` |
| `QWC_RPC_USERNAME_FILE` / `QWC_RPC_PASSWORD_FILE` | empty | Mounted secret files for Digest auth |
| `QWC_EXPECTED_CORE_VERSION` | `2.0.2-release` | Exact allowed Core version |
| `QWC_EXPECTED_GENESIS_HASH` | QWC Mainnet genesis | Exact source-chain binding |
| `POLL_INTERVAL_SECONDS` | `300` | Collection interval |
| `STALE_AFTER_SECONDS` | `900` | Age after which a snapshot is stale; must exceed polling |
| `GEOIP_DB_PATH` | `/data/geoip/dbip-city-lite.mmdb` | Local MMDB path |
| `GEOIP_AUTO_UPDATE` | `true` | Download/check DB-IP City Lite automatically |
| `DATA_DIR` | `/data` | Persistent aggregate data directory |
| `HTTP_HOST` / `HTTP_PORT` | `0.0.0.0` / `8080` | Application listener |
| `PUBLIC_BASE_PATH` | empty | Root operation or a value such as `/node-map` |
| `CORS_ALLOWED_ORIGINS` | empty | Comma-separated exact origins; Same-Origin is the default |

Malformed settings are rejected at startup. Secrets and internal URLs are not returned through public errors.

## GeoIP data

With automatic updates enabled, the service downloads the current DB-IP City Lite MMDB over HTTPS, tries the previous month if the new monthly file is not available yet, enforces compressed/decompressed size limits, validates the MMDB and atomically replaces the old reader. A failed update leaves the last valid database in use.

To provision the database yourself, mount it at `GEOIP_DB_PATH` and set `GEOIP_AUTO_UPDATE=false`. The web page includes the attribution required by DB-IP.

## API and health semantics

- `GET /api/v1/map`: one consistent, aggregate-only schema-v1 snapshot;
- `GET /api/v1/history?window=30d|7d|24h`: distinct public peer IPs retained and re-aggregated for the selected period (default `30d`);
- `GET /healthz`: process health; it performs no RPC request;
- `GET /readyz`: HTTP 200 only with a recent successful snapshot and a functioning collector.

With a previously valid snapshot, `/api/v1/map` stays HTTP 200 and exposes explicit `error`/`stale` metadata. Before any complete collection it returns HTTP 503 with unknown metrics represented as `null`, never false zeroes. See [the API contract](docs/API.md).

## Development and tests

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pytest
```

The test suite covers address normalization, IPv4-mapped IPv6, deduplication, handshake states, private/CGNAT/link-local/multicast exclusion, anonymous networks, aggregation invariants, real MMDB reading, source-bound persistence, RPC/schema failures, root/subpath operation and stale-snapshot preservation. CI also runs a Docker smoke test against a controlled mock RPC source.

## Operations and rollback

- Persistent state is confined to the Docker volume mounted at `/data`. This includes the source-bound history database and its mode-`0600` HMAC key; preserve both together across container replacements.
- The image runs as UID/GID 10001, with a read-only root filesystem, all Linux capabilities dropped and no Docker socket.
- One worker owns one scheduler, so collector runs cannot multiply across workers.
- To roll back, stop the replacement container and restart the prior image with the same `/data` volume. Aggregate snapshots remain compatible as schema version 1. A first history-enabled deployment starts an honest partial window and fills the complete 30-day view over time; prior observations cannot be reconstructed.
- A source URL/network/genesis change invalidates the old snapshot automatically instead of silently reusing it.

For proxy and Explorer reuse examples, see [Explorer integration](docs/EXPLORER_INTEGRATION.md). Third-party licenses and attribution are documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
