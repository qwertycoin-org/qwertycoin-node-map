# Explorer integration

The collector, schema and visual component are independent of a deployment hostname.

## Same-origin proxy

Recommended Explorer route:

```nginx
location /node-map/ {
    proxy_pass http://127.0.0.1:18082/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_hide_header Access-Control-Allow-Origin;
}
```

Alternatively run the application with `PUBLIC_BASE_PATH=/node-map` and preserve that path at the proxy. Validate asset, API and redirect behavior for the selected mode; do not combine path stripping with an application subpath.

## Reusable map component

Serve Leaflet, `node-map.js` and `countries.geojson` locally from the Explorer. Mount the component with an explicitly supplied API path, fetch `/node-map/api/v1/map`, then pass `snapshot.markers` to `map.render()`.

The Explorer must reuse the aggregate API; it must never proxy arbitrary browser requests to the unrestricted daemon RPC. Keep the component CSS scoped and retain DB-IP/Natural Earth attribution.
