from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


HANDSHAKE_COMPLETE_STATES = {"synchronizing", "standby", "idle", "normal"}
ANONYMOUS_ADDRESS_TYPES = {"tor", "i2p"}


@dataclass(frozen=True, slots=True)
class NormalizedPeers:
    public_ips: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]
    anonymous_connections: int
    excluded_connections: int


def _nonzero_peer_id(value: Any) -> bool:
    text = str(value or "").strip().lower().removeprefix("0x")
    return bool(text) and any(char != "0" for char in text)


def _candidate_host(connection: dict[str, Any]) -> str | None:
    for key in ("host", "ip"):
        value = connection.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().strip("[]")
    address = connection.get("address")
    if not isinstance(address, str) or not address.strip():
        return None
    try:
        return urlsplit(f"//{address.strip()}").hostname
    except ValueError:
        return None


def normalize_connections(connections: list[dict[str, Any]]) -> NormalizedPeers:
    public: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    anonymous = 0
    excluded = 0
    for connection in connections:
        state = str(connection.get("state", "")).strip().lower()
        if state not in HANDSHAKE_COMPLETE_STATES or not _nonzero_peer_id(connection.get("peer_id")):
            excluded += 1
            continue
        address_type = str(connection.get("address_type", "")).strip().lower()
        host = _candidate_host(connection)
        if address_type in ANONYMOUS_ADDRESS_TYPES or (host and host.lower().endswith((".onion", ".i2p"))):
            anonymous += 1
            continue
        if host is None:
            excluded += 1
            continue
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            excluded += 1
            continue
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if (
            not address.is_global
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
            or address.is_loopback
            or address.is_link_local
            or address.is_private
        ):
            excluded += 1
            continue
        public.add(address)
    return NormalizedPeers(
        public_ips=tuple(sorted(public, key=lambda item: (item.version, int(item)))),
        anonymous_connections=anonymous,
        excluded_connections=excluded,
    )
