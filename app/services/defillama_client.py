from __future__ import annotations

import httpx


class DefiLlamaClient:
    """Thin client for the DefiLlama Bridges API (https://bridges.llama.fi)."""

    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def fetch_bridges(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{self._base_url}/bridges")
            response.raise_for_status()
            data = response.json()
        if isinstance(data, dict):
            return data.get("bridges", [])
        if isinstance(data, list):
            return data
        return []
