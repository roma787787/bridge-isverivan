from __future__ import annotations

import asyncio
import logging

from .cache import CacheClient
from .lifi_client import LiFiClient

logger = logging.getLogger(__name__)

_MIN_CHAINS_TO_INDEX = 2

# Cosmetic renames for chains Li.Fi labels differently than users expect.
# Any chain not listed here is indexed under its own Li.Fi name as-is, so
# tracking a new chain never requires touching this file — coverage grows
# automatically as Li.Fi adds mainnets.
_CHAIN_NAME_OVERRIDES: dict[str, str] = {
    "bsc": "BNB Chain",
    "binance smart chain": "BNB Chain",
    "bnb smart chain": "BNB Chain",
    "op mainnet": "Optimism",
    "polygon pos": "Polygon",
    "arbitrum one": "Arbitrum",
    "avalanche c-chain": "Avalanche",
    "gnosis chain": "Gnosis",
    "xdai": "Gnosis",
    "zksync": "zkSync Era",
}


def _display_name(raw_name: str) -> str:
    normalized = raw_name.strip()
    return _CHAIN_NAME_OVERRIDES.get(normalized.lower(), normalized)


class TokenIndexSyncService:
    """Builds a ticker -> [networks] index across every mainnet Li.Fi tracks.

    Unlike the curated bridge dataset (a hand-picked ~10 tokens), this aims
    for broad coverage: essentially any actively traded tier-1/2/3 token that
    exists on 2+ of Li.Fi's tracked chains gets indexed, which is what lets
    the bot resolve tickers far beyond the curated list instead of reporting
    "not found" for anything not hand-picked. Any failure here (Li.Fi down,
    unexpected response shape, timeout) is swallowed and logged — the
    previous index (or none) is kept, and curated tickers keep working
    regardless.
    """

    def __init__(self, client: LiFiClient, cache: CacheClient, interval_hours: float) -> None:
        self._client = client
        self._cache = cache
        self._interval_seconds = interval_hours * 3600

    async def sync_once(self) -> None:
        try:
            chains = await self._client.fetch_chains()
            chain_ids = self._mainnet_chain_ids(chains)
            if not chain_ids:
                logger.warning("Token index sync: no chains resolved from Li.Fi, skipping")
                return
            tokens_by_chain = await self._client.fetch_tokens_by_chain(chain_ids)
        except Exception as exc:
            logger.warning("Token index sync failed, keeping previous data: %s", exc)
            return

        name_by_id = {
            str(chain.get("id")): _display_name(str(chain.get("name", "")))
            for chain in chains
            if chain.get("id") is not None and chain.get("name")
        }

        index: dict[str, set[str]] = {}
        for chain_id, tokens in tokens_by_chain.items():
            network = name_by_id.get(str(chain_id))
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
            logger.info(
                "Token index sync complete: %d tickers indexed across %d chains", len(filtered), len(chain_ids)
            )
        else:
            logger.warning("Token index sync produced no eligible tickers, keeping previous data")

    def _mainnet_chain_ids(self, chains: list[dict]) -> list[str]:
        ids = []
        for chain in chains:
            if chain.get("id") is None:
                continue
            if chain.get("mainnet", True) is False:
                continue
            ids.append(str(chain["id"]))
        return ids

    async def run_forever(self) -> None:
        while True:
            await self.sync_once()
            await asyncio.sleep(self._interval_seconds)
