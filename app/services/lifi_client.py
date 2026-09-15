from __future__ import annotations

import httpx


class LiFiClient:
    """Thin client for the public Li.Fi API (https://li.quest).

    Used to discover, for an arbitrary ticker, which chains it actually
    exists on — this is what lets the bot answer for tokens outside the
    curated bridge dataset instead of only recognizing a fixed short list.
    """

    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def fetch_chains(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{self._base_url}/v1/chains")
            response.raise_for_status()
            data = response.json()
        return data.get("chains", []) if isinstance(data, dict) else []

    async def fetch_tokens_by_chain(self, chain_ids: list[str]) -> dict[str, list[dict]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/v1/tokens", params={"chains": ",".join(chain_ids)}
            )
            response.raise_for_status()
            data = response.json()
        return data.get("tokens", {}) if isinstance(data, dict) else {}
