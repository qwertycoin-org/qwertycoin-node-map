from app.peers import normalize_connections


def connection(host: str, *, state: str = "normal", peer_id: str = "1234", address_type: str = "IPv4") -> dict:
    return {"host": host, "state": state, "peer_id": peer_id, "address_type": address_type}


def test_normalizes_deduplicates_and_includes_synchronizing_peers():
    result = normalize_connections([
        connection("8.8.8.8"),
        connection("8.8.8.8"),
        connection("::ffff:8.8.8.8"),
        connection("2001:4860:4860::8888", state="synchronizing", address_type="IPv6"),
        connection("1.1.1.1", state="before_handshake"),
        connection("9.9.9.9", peer_id="0000000000000000"),
    ])
    assert [str(value) for value in result.public_ips] == ["8.8.8.8", "2001:4860:4860::8888"]
    assert result.excluded_connections == 2


def test_excludes_non_global_and_separates_anonymous_connections():
    result = normalize_connections([
        connection("10.0.0.1"),
        connection("100.64.0.1"),
        connection("127.0.0.1"),
        connection("169.254.1.1"),
        connection("224.0.0.1"),
        connection("::1", address_type="IPv6"),
        connection("examplehiddenservice.onion", address_type="Tor"),
        connection("example.i2p", address_type="I2P"),
    ])
    assert result.public_ips == ()
    assert result.anonymous_connections == 2
    assert result.excluded_connections == 6


def test_address_fallback_parses_ipv6_without_colon_splitting():
    result = normalize_connections([
        {"address": "[2001:4860:4860::8844]:8196", "state": "normal", "peer_id": "1", "address_type": "IPv6"},
        {"address": "8.8.4.4:8196", "state": "idle", "peer_id": "2", "address_type": "IPv4"},
    ])
    assert [str(value) for value in result.public_ips] == ["8.8.4.4", "2001:4860:4860::8844"]
