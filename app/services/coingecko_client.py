from __future__ import annotations

import httpx

# CoinGecko asset-platform ids we recognize, mapped to our canonical network
# names. Deliberately conservative: an unrecognized platform id is skipped
# rather than shown under a raw/ugly slug, since this client backs an
# on-demand fallback where a wrong-looking network name is worse than an
# undercount.
_PLATFORM_TO_NETWORK: dict[str, str] = {
    "ethereum": "Ethereum",
    "binance-smart-chain": "BNB Chain",
    "polygon-pos": "Polygon",
    "arbitrum-one": "Arbitrum",
    "optimistic-ethereum": "Optimism",
    "avalanche": "Avalanche",
    "base": "Base",
    "linea": "Linea",
    "zksync": "zkSync Era",
    "solana": "Solana",
    "xdai": "Gnosis",
    "fantom": "Fantom",
    "near-protocol": "NEAR",
    "polkadot": "Polkadot",
    "cosmos": "Cosmos Hub",
    "the-open-network": "TON",
}


class CoinGeckoClient:
    """On-demand fallback lookup via the free CoinGecko API.

    Used only when a ticker isn't in the curated dataset and isn't in the
    Li.Fi-derived auto-detected index. CoinGecko's per-project ``platforms``
    field lists canonical contract addresses per chain for one verified
    project (chosen by market cap rank among same-symbol matches), which
    resolves cases the raw per-chain Li.Fi token scan misses or would risk
    a symbol collision on.
    """

    def __init__(self, base_url: str, timeout_seconds: float, api_key: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        # A bare httpx default User-Agent gets bot-blocked (403) by some
        # CoinGecko edge nodes; a normal-looking browser-ish UA avoids that
        # without needing an API key.
        self._headers = {"User-Agent": "Mozilla/5.0 (compatible; BridgeFinderBot/1.0)"}
        # Fully anonymous access to api.coingecko.com is heavily throttled
        # (and increasingly likely to just 429/403 from a shared cloud IP
        # like Railway's). A free Demo API key (from coingecko.com/en/api)
        # gets a real, documented rate limit via this header — same host,
        # no code path change beyond adding it.
        if api_key:
            self._headers["x-cg-demo-api-key"] = api_key

    async def find_networks(self, ticker: str) -> list[str]:
        coin_id = await self._resolve_coin_id(ticker)
        if not coin_id:
            return []
        platforms = await self._fetch_platforms(coin_id)
        networks = {_PLATFORM_TO_NETWORK[platform] for platform in platforms if platform in _PLATFORM_TO_NETWORK}
        return sorted(networks)

    async def _resolve_coin_id(self, ticker: str) -> str | None:
        async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as client:
            response = await client.get(f"{self._base_url}/search", params={"query": ticker})
            response.raise_for_status()
            data = response.json()

        candidates = [
            coin for coin in data.get("coins", []) if str(coin.get("symbol", "")).strip().upper() == ticker
        ]
        if not candidates:
            return None

        def rank_key(coin: dict) -> float:
            rank = coin.get("market_cap_rank")
            return rank if isinstance(rank, (int, float)) else float("inf")

        best = min(candidates, key=rank_key)
        return best.get("id")

    async def _fetch_platforms(self, coin_id: str) -> dict[str, str]:
        async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as client:
            response = await client.get(
                f"{self._base_url}/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "false",
                    "community_data": "false",
                    "developer_data": "false",
                    "sparkline": "false",
                },
            )
            response.raise_for_status()
            data = response.json()
        return data.get("platforms", {}) or {}
