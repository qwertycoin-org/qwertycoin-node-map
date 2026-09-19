from __future__ import annotations

import ipaddress
from collections import Counter
from dataclasses import dataclass
from typing import Protocol


class GeoResolver(Protocol):
    def lookup(self, address: str) -> dict | None: ...


@dataclass(frozen=True, slots=True)
class AggregateResult:
    countries: list[dict]
    markers: list[dict]
    unique_public_ips: int
    country_count: int
    unknown_country_ips: int
    non_mappable_public_ips: int


@dataclass(frozen=True, slots=True)
class LocatedPeer:
    address: str
    country_code: str
    country_name: str
    latitude: float | None
    longitude: float | None


def locate_ips(
    addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...], resolver: GeoResolver
) -> tuple[LocatedPeer, ...]:
    located: list[LocatedPeer] = []
    for address in addresses:
        record = resolver.lookup(str(address)) or {}
        country = record.get("country") if isinstance(record, dict) else None
        country = country if isinstance(country, dict) else {}
        code = str(country.get("iso_code", "")).upper()
        names = country.get("names") if isinstance(country.get("names"), dict) else {}
        name = str(names.get("en", "")).strip()
        if len(code) != 2:
            code, name = "ZZ", "Unknown"
        elif not name:
            name = code

        location = record.get("location") if isinstance(record, dict) else None
        location = location if isinstance(location, dict) else {}
        latitude = location.get("latitude")
        longitude = location.get("longitude")
        if (
            code == "ZZ"
            or not isinstance(latitude, (int, float))
            or not isinstance(longitude, (int, float))
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            latitude = longitude = None
        else:
            latitude = round(float(latitude), 1)
            longitude = round(float(longitude), 1)
        located.append(LocatedPeer(str(address), code, name, latitude, longitude))
    return tuple(located)


def aggregate_locations(located: tuple[LocatedPeer, ...]) -> AggregateResult:
    countries: Counter[tuple[str, str]] = Counter()
    markers: Counter[tuple[str, float, float]] = Counter()
    unknown_country = 0
    non_mappable = 0

    for peer in located:
        countries[(peer.country_code, peer.country_name)] += 1
        if peer.country_code == "ZZ":
            unknown_country += 1
        if peer.latitude is None or peer.longitude is None:
            non_mappable += 1
            continue
        markers[(peer.country_code, peer.latitude, peer.longitude)] += 1

    total = len(located)
    country_rows = [
        {"code": code, "name": name, "count": count, "share_percent": round(count * 100 / total, 1) if total else 0.0}
        for (code, name), count in sorted(countries.items(), key=lambda item: (-item[1], item[0][1]))
    ]
    marker_rows = [
        {"country_code": code, "latitude": lat, "longitude": lon, "count": count}
        for (code, lat, lon), count in sorted(markers.items(), key=lambda item: (-item[1], item[0]))
    ]
    if sum(row["count"] for row in country_rows) != total:
        raise RuntimeError("country aggregation invariant failed")
    if sum(row["count"] for row in marker_rows) + non_mappable != total:
        raise RuntimeError("marker aggregation invariant failed")
    return AggregateResult(
        countries=country_rows,
        markers=marker_rows,
        unique_public_ips=total,
        country_count=len({row["code"] for row in country_rows if row["code"] != "ZZ"}),
        unknown_country_ips=unknown_country,
        non_mappable_public_ips=non_mappable,
    )


def aggregate_ips(
    addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...], resolver: GeoResolver
) -> AggregateResult:
    return aggregate_locations(locate_ips(addresses, resolver))
