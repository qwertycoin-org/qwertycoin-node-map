#!/usr/bin/env bash
set -euo pipefail

network="qwc-node-map-smoke-${GITHUB_RUN_ID:-local}"
mock="qwc-node-map-mock-${GITHUB_RUN_ID:-local}"
app="qwc-node-map-app-${GITHUB_RUN_ID:-local}"
data_dir="${RUNNER_TEMP:-/tmp}/qwc-node-map-smoke-${GITHUB_RUN_ID:-local}"

cleanup() {
  docker rm -f "$app" "$mock" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}
trap cleanup EXIT

install -d -m 0777 "$data_dir" "$data_dir/geoip"
install -m 0644 tests/fixtures/GeoIP2-City-Test.mmdb "$data_dir/geoip/dbip-city-lite.mmdb"
docker network create "$network" >/dev/null
docker run --detach --name "$mock" --network "$network" --read-only --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,src=$PWD/tests/mock_rpc_server.py,dst=/mock.py,readonly" \
  python:3.13.13-slim-bookworm@sha256:f576b530293e74140ea91d262232648d5c4f45640a95ec447757701bfcacf034 python /mock.py >/dev/null

docker run --detach --name "$app" --network "$network" -p 127.0.0.1:18083:8080 \
  --read-only --cap-drop ALL --security-opt no-new-privileges --memory 512m --pids-limit 128 \
  --tmpfs /tmp:size=64m,mode=1777 --mount "type=bind,src=$data_dir,dst=/data" \
  -e QWC_RPC_BASE_URL=http://"$mock":8197 -e GEOIP_AUTO_UPDATE=false qwertycoin-node-map:test >/dev/null

for attempt in $(seq 1 30); do
  if curl --silent --fail http://127.0.0.1:18083/readyz >/dev/null; then break; fi
  if [ "$attempt" -eq 30 ]; then docker logs "$app"; exit 1; fi
  sleep 1
done

curl --silent --fail http://127.0.0.1:18083/api/v1/map > "$data_dir/result.json"
jq -e '.schema_version == 1 and .network == "mainnet" and .summary.observed_public_ips == 1 and .summary.excluded_connections == 1' "$data_dir/result.json" >/dev/null
curl --silent --fail 'http://127.0.0.1:18083/api/v1/history?window=30d' > "$data_dir/history.json"
jq -e '.schema_version == 1 and .scope == "single_observer_history" and .window == "30d" and .summary.observed_public_ips == 1' "$data_dir/history.json" >/dev/null
if grep -Eq '81\.2\.69\.160|peer_id|qwc-node-map-mock' "$data_dir/result.json" "$data_dir/history.json"; then
  echo "Public API leaked raw collector data" >&2
  exit 1
fi
curl --silent --fail http://127.0.0.1:18083/ >/dev/null
curl --silent --fail http://127.0.0.1:18083/assets/node-map.js >/dev/null
test "$(docker inspect -f '{{.State.Restarting}}' "$app")" = "false"
