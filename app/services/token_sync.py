from __future__ import annotations

import asyncio
import logging

from .cache import CacheClient
from .lifi_client import LiFiClient

logger = logging.getLogger(__name__)

# Normalized (lowercase) Li.Fi chain name -> canonical network name, matching
# the spelling used in bridges_seed.json so intersections line up.
_CHAIN_NAME_ALIASES: dict[str, str] = {
    "ethereum": "Ethereum",
    "eth": "Ethereum",
    "arbitrum": "Arbitrum",
    "arbitrum one": "Arbitrum",
    "optimism": "Optimism",
    "op mainnet": "Optimism",
    "polygon": "Polygon",
    "polygon pos": "Polygon",
    "bnb chain": "BNB Chain",
    "bsc": "BNB Chain",
    "bnb smart chain": "BNB Chain",
    "binance smart chain": "BNB Chain",
    "avalanche": "Avalanche",
    "avalanche c-chain": "Avalanche",
    "base": "Base",
    "linea": "Linea",
    "zksync era": "zkSync Era",
    "zksync": "zkSync Era",
    "solana": "Solana",
    "gnosis": "Gnosis",
    "gnosis chain": "Gnosis",
    "xdai": "Gnosis",
    "fantom": "Fantom",
}

_MIN_CHAINS_TO_INDEX = 2


class TokenIndexSyncService:
    """Builds a best-effort ticker -> [networks] index from the Li.Fi token list.

    This complements ``bridges_seed.json``: a ticker that isn't curated but
    exists on 2+ chains we track becomes searchable through
    ``BridgeRepository``'s auto-detected layer, so the bot can answer for a
    much wider range of tickers instead of only the handful that are
    manually curated. Any failure here (Li.Fi down, unexpected response
    shape, timeout) is swallowed and logged — the previous index (or none)
    is kept, and curated tickers keep working regardless.
    """

    def __init__(self, client: LiFiClient, cache: CacheClient, interval_hours: float) -> None:
        self._client = client
        self._cache = cache
        self._interval_seconds = interval_hours * 3600

    async def sync_once(self) -> None:
        try:
            chains = await self._client.fetch_chains()
            chain_ids = self._relevant_chain_ids(chains)
            if not chain_ids:
                logger.warning("Token index sync: no relevant chains resolved from Li.Fi, skipping")
                return
            tokens_by_chain = await self._client.fetch_tokens_by_chain(chain_ids)
        except Exception as exc:
            logger.warning("Token index sync failed, keeping previous data: %s", exc)
            return

        chain_name_by_id = {
            str(chain.get("id")): _CHAIN_NAME_ALIASES.get(str(chain.get("name", "")).strip().lower())
            for chain in chains
        }

        index: dict[str, set[str]] = {}
        for chain_id, tokens in tokens_by_chain.items():
            network = chain_name_by_id.get(str(chain_id))
            if not network:
                continue
            for token in tokens:
                symbol = str(token.get("symbol", "")).strip().upper()
                if not symbol:
                    continue
                index.setdefault(symbol, set()).add(network)

        filtered = {
            symbol: sorted(networks) for symbol, networks in index.items() if len(networks) >= _MIN_CHAINS_TO_INDEX
        }

        if filtered:
            await self._cache.set_token_index(filtered)
            logger.info("Token index sync complete: %d tickers indexed", len(filtered))
        else:
            logger.warning("Token index sync produced no eligible tickers, keeping previous data")

    def _relevant_chain_ids(self, chains: list[dict]) -> list[str]:
        ids = []
        for chain in chains:
            name = str(chain.get("name", "")).strip().lower()
            if name in _CHAIN_NAME_ALIASES and chain.get("id") is not None:
                ids.append(str(chain["id"]))
        return ids

    async def run_forever(self) -> None:
        while True:
            await self.sync_once()
            await asyncio.sleep(self._interval_seconds)
