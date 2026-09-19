import json
from dataclasses import replace

import httpx
import pytest

from app.rpc import QwcRpcClient, RpcError


@pytest.mark.asyncio
async def test_validates_mainnet_version_genesis_and_connections(settings):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method = payload["method"]
        if method == "get_info":
            result = {"status": "OK", "mainnet": True, "version": "2.0.2-release"}
        elif method == "get_block_header_by_height":
            result = {"status": "OK", "block_header": {"hash": settings.expected_genesis_hash}}
        elif method == "get_connections":
            result = {"status": "OK", "connections": [{"host": "192.0.2.1"}]}
        else:
            return httpx.Response(500)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": "node-map", "result": result})

    rpc = QwcRpcClient(settings)
    await rpc._client.aclose()
    rpc._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert await rpc.validate_source(settings) == {"network": "mainnet", "core_version": "2.0.2-release"}
    assert len(await rpc.connections()) == 1
    await rpc.close()


@pytest.mark.asyncio
async def test_rejects_json_rpc_error(settings):
    rpc = QwcRpcClient(settings)
    await rpc._client.aclose()
    rpc._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"error": {"code": -1}}))
    )
    with pytest.raises(RpcError, match="JSON-RPC error"):
        await rpc.call("get_connections")
    await rpc.close()


@pytest.mark.asyncio
async def test_rejects_oversized_response(settings):
    limited = replace(settings, rpc_max_response_bytes=128)
    rpc = QwcRpcClient(limited)
    await rpc._client.aclose()
    rpc._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 129))
    )
    with pytest.raises(RpcError, match="size limit"):
        await rpc.call("get_connections")
    await rpc.close()


@pytest.mark.asyncio
async def test_missing_connections_is_not_a_false_zero(settings):
    rpc = QwcRpcClient(settings)
    await rpc._client.aclose()
    rpc._client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"result": {"status": "OK"}})
        )
    )
    with pytest.raises(RpcError, match="connections field"):
        await rpc.connections()
    await rpc.close()
