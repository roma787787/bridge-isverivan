from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cache import CacheClient

_SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "bridges_seed.json"
_MIN_NETWORKS_FOR_AUTO_MATCH = 2

# Curated entries with few bridges (typically native non-EVM chains like
# TON/BTC/DOT that only have one official/trustless bridge) are topped up
# with the auto-detected aggregator layer when it surfaces networks the
# curated entry doesn't already cover — e.g. a wrapped version of the token
# tradeable on extra EVM chains. Well-covered tickers (USDT, ETH, ...) are
# left alone so the reply doesn't balloon with redundant network lists.
_SUPPLEMENT_CURATED_BELOW = 3

# General-purpose cross-chain swap+bridge aggregators. Unlike the curated
# liquidity bridges above (which only route a pre-whitelisted set of
# tokens), these route arbitrary ERC-20/SPL tokens by combining DEX
# liquidity with whichever underlying bridge is available — so they are a
# realistic recommendation for a token we only know "exists on N chains"
# without knowing which specific liquidity bridge supports it.
_GENERAL_AGGREGATORS: list[dict[str, str]] = [
    {"key": "lifi", "display_name": "LI.FI (Jumper)", "url": "https://jumper.exchange"},
    {"key": "rango", "display_name": "Rango Exchange", "url": "https://app.rango.exchange"},
    {"key": "bungee", "display_name": "Bungee (Socket)", "url": "https://bungee.exchange"},
    {"key": "squid-aggregator", "display_name": "Squid Router", "url": "https://app.squidrouter.com"},
]


@dataclass(frozen=True)
class BridgeInfo:
    key: str
    display_name: str
    url: str
    networks: list[str]
    auto_detected: bool = False


class BridgeRepository:
    """Resolves which bridges support a given token ticker.

    Two layers of data are combined:

    1. A curated reference dataset (``bridges_seed.json``) mapping tickers to
       bridges and each bridge's official site — precise, but only covers a
       hand-picked set of well-known tokens.
    2. An auto-detected layer built by ``services.token_sync`` from the
       Li.Fi token list: any ticker that exists on 2+ chains we track (which
       covers the vast majority of actively traded tier-1/2/3 tokens, not
       just a hand-picked set) is reported as reachable via general-purpose
       cross-chain aggregators, together with the actual networks it was
       found on. Results from this layer are flagged via
       ``BridgeInfo.auto_detected`` and the bot tells the user to double
       check the exact route before transferring.

    A curated entry with few bridges (typically a native non-EVM chain like
    TON/BTC/DOT that only has one official bridge) is topped up with any
    auto-detected networks not already covered — e.g. a wrapped version of
    the token tradeable on extra EVM chains — instead of the curated match
    hiding that information. Well-covered curated tickers are left as-is.

    Either layer degrades gracefully to "not found" if its data is missing —
    curated data always ships with the app, and the auto-detected layer is
    simply absent until the first successful background sync.
    """

    def __init__(self, cache: CacheClient, seed_path: Path = _SEED_PATH) -> None:
        with open(seed_path, "r", encoding="utf-8") as fh:
            seed: dict[str, Any] = json.load(fh)

        self._tokens: dict[str, list[str]] = {
            ticker.upper(): data["bridges"] for ticker, data in seed["tokens"].items()
        }
        self._bridges: dict[str, dict[str, Any]] = seed["bridges"]
        self._cache = cache

    def bridge_keys(self) -> set[str]:
        return set(self._bridges.keys())

    def all_known_tickers(self) -> list[str]:
        return list(self._tokens.keys())

    async def _networks_for(self, bridge_key: str) -> list[str]:
        bridge = self._bridges[bridge_key]
        live_chains = await self._cache.get_bridge_chains(bridge_key)
        if not live_chains:
            return list(bridge["networks"])

        merged = list(bridge["networks"])
        for chain in live_chains:
            if chain not in merged:
                merged.append(chain)
        return merged

    async def find_bridges_for_ticker(self, ticker: str) -> list[BridgeInfo] | None:
        ticker = ticker.upper()

        curated = await self._find_curated(ticker)
        if curated is None:
            return await self._find_auto_detected(ticker)

        if len(curated) >= _SUPPLEMENT_CURATED_BELOW:
            return curated

        auto_detected = await self._find_auto_detected(ticker)
        if not auto_detected:
            return curated

        curated_networks = {network for bridge in curated for network in bridge.networks}
        extra_networks = set(auto_detected[0].networks) - curated_networks
        if not extra_networks:
            return curated

        return curated + auto_detected

    async def _find_curated(self, ticker: str) -> list[BridgeInfo] | None:
        bridge_keys = self._tokens.get(ticker)
        if not bridge_keys:
            return None

        result: list[BridgeInfo] = []
        for key in bridge_keys:
            bridge = self._bridges[key]
            networks = await self._networks_for(key)
            result.append(
                BridgeInfo(key=key, display_name=bridge["display_name"], url=bridge["url"], networks=networks)
            )
        return result

    async def _find_auto_detected(self, ticker: str) -> list[BridgeInfo] | None:
        index = await self._cache.get_token_index()
        if not index:
            return None

        networks = sorted(index.get(ticker, []))
        if len(networks) < _MIN_NETWORKS_FOR_AUTO_MATCH:
            return None

        return [
            BridgeInfo(
                key=aggregator["key"],
                display_name=aggregator["display_name"],
                url=aggregator["url"],
                networks=networks,
                auto_detected=True,
            )
            for aggregator in _GENERAL_AGGREGATORS
        ]

    async def suggest_tickers(self, raw: str, limit: int = 3) -> list[str]:
        known = set(self.all_known_tickers())
        index = await self._cache.get_token_index()
        if index:
            known |= set(index.keys())
        return difflib.get_close_matches(raw.upper(), known, n=limit, cutoff=0.5)
