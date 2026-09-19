from __future__ import annotations

import json
from typing import Any

import httpx

from .config import Settings


class RpcError(RuntimeError):
    """An intentionally non-sensitive RPC failure."""


class QwcRpcClient:
    def __init__(self, settings: Settings) -> None:
        auth = None
        if settings.rpc_auth == "digest":
            auth = httpx.DigestAuth(settings.rpc_username or "", settings.rpc_password or "")
        self._url = f"{settings.rpc_base_url}/json_rpc"
        self._limit = settings.rpc_max_response_bytes
        self._client = httpx.AsyncClient(
            auth=auth,
            timeout=httpx.Timeout(connect=3.0, read=10.0, write=10.0, pool=3.0),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": "qwertycoin-node-map/1"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        body = {"jsonrpc": "2.0", "id": "node-map", "method": method}
        if params is not None:
            body["params"] = params
        try:
            async with self._client.stream("POST", self._url, json=body) as response:
                if response.status_code != 200:
                    raise RpcError(f"RPC returned HTTP {response.status_code}")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > self._limit:
                        raise RpcError("RPC response exceeded the configured size limit")
        except RpcError:
            raise
        except httpx.HTTPError as exc:
            raise RpcError("RPC request failed") from exc
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RpcError("RPC returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RpcError("RPC response was not an object")
        if payload.get("error") is not None:
            raise RpcError("RPC returned a JSON-RPC error")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise RpcError("RPC result was not an object")
        status = result.get("status")
        if status is not None and status != "OK":
            raise RpcError("RPC status was not OK")
        return result

    async def validate_source(self, settings: Settings) -> dict[str, Any]:
        info = await self.call("get_info")
        if info.get("mainnet") is not True:
            raise RpcError("RPC source is not Qwertycoin mainnet")
        version = str(info.get("version", ""))
        if settings.expected_core_version and version != settings.expected_core_version:
            raise RpcError("RPC source version does not match the configured version")
        genesis = await self.call("get_block_header_by_height", {"height": 0})
        header = genesis.get("block_header")
        if not isinstance(header, dict) or str(header.get("hash", "")).lower() != settings.expected_genesis_hash:
            raise RpcError("RPC source genesis does not match Qwertycoin mainnet")
        return {"network": "mainnet", "core_version": version}

    async def connections(self) -> list[dict[str, Any]]:
        result = await self.call("get_connections")
        connections = result.get("connections")
        if not isinstance(connections, list):
            raise RpcError("RPC connections field was missing or invalid")
        if not all(isinstance(item, dict) for item in connections):
            raise RpcError("RPC connections contained an invalid entry")
        return connections

