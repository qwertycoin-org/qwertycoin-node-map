import ipaddress

from app.aggregate import aggregate_ips


class Resolver:
    records = {
        "8.8.8.8": {"country": {"iso_code": "US", "names": {"en": "United States"}}, "location": {"latitude": 37.4, "longitude": -122.1}},
        "1.1.1.1": {"country": {"iso_code": "AU", "names": {"en": "Australia"}}},
        "9.9.9.9": {},
    }

    def lookup(self, address):
        return self.records.get(address)


def test_aggregation_invariants_and_unknown_values():
    addresses = tuple(ipaddress.ip_address(value) for value in ("8.8.8.8", "1.1.1.1", "9.9.9.9"))
    result = aggregate_ips(addresses, Resolver())
    assert result.unique_public_ips == 3
    assert result.country_count == 2
    assert result.unknown_country_ips == 1
    assert result.non_mappable_public_ips == 2
    assert sum(row["count"] for row in result.countries) == 3
    assert sum(row["count"] for row in result.markers) + result.non_mappable_public_ips == 3
    assert result.markers == [{"country_code": "US", "latitude": 37.4, "longitude": -122.1, "count": 1}]


def test_empty_measurement_is_a_valid_zero():
    result = aggregate_ips((), Resolver())
    assert result.unique_public_ips == 0
    assert result.countries == []
    assert result.markers == []
    assert result.non_mappable_public_ips == 0
