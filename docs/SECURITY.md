# Security and privacy model

- Every RPC field is untrusted; oversized, malformed and unsuccessful responses are rejected.
- IPs are parsed with the standard library, canonicalized, deduplicated and explicitly filtered for global routability.
- Raw connections, IP addresses and peer IDs exist only during one in-memory collection. They are never persisted, logged or returned.
- Persisted aggregate snapshots are bound to the configured source URL, network and genesis.
- The service never connects to peer-provided addresses or resolves peer hostnames.
- The unrestricted Core RPC stays private. Browsers can access only the aggregate API.
- GeoIP downloads use a fixed HTTPS provider path, bounded streaming, validation and atomic replacement.
- The container has no Docker socket, no capabilities, a non-root UID and a read-only root filesystem.
- Browser content is local and protected by a restrictive Content Security Policy; there are no third-party tiles, fonts, scripts or analytics.
