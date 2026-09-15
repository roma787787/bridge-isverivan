from __future__ import annotations

import asyncio
import difflib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cache import CacheClient
from .coingecko_client import CoinGeckoClient

logger = logging.getLogger(__name__)

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

# Manual fallback for well-known tickers whose multi-chain existence is not
# reliably reflected in Li.Fi's free token feed (it can list a token only
# under its own native chain even when the token demonstrably also exists
# elsewhere, e.g. an L2 governance token that's canonically bridged from
# Ethereum). Only add an entry here when you are certain the ticker exists
# natively on every listed network — this is used as a last resort when the
# live index doesn't already have 2+ networks for the ticker.
_MANUAL_NETWORK_FALLBACKS: dict[str, list[str]] = {
    "OP": ["Ethereum", "Optimism"],
}


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
       check the exact route before transferring. A small manual fallback
       table (``_MANUAL_NETWORK_FALLBACKS``) covers well-known tickers that
       Li.Fi's free token feed doesn't reliably list on 2+ chains.
    3. An on-demand CoinGecko lookup, tried only when neither of the above
       resolves anything. CoinGecko's per-project ``platforms`` field is a
       canonical, verified chain list for one specific project (picked by
       market cap rank among same-symbol matches), so it catches gaps in
       Li.Fi's per-chain token scan without the same symbol-collision risk.
       It runs live at request time under a strict timeout and its result
       (including "found nothing") is cached to avoid repeatedly hitting
       CoinGecko's rate-limited free tier for the same ticker.

    A curated entry with few bridges (typically a native non-EVM chain like
    TON/BTC/DOT that only has one official bridge) is topped up with any
    auto-detected networks not already covered — e.g. a wrapped version of
    the token tradeable on extra EVM chains — instead of the curated match
    hiding that information. Well-covered curated tickers are left as-is.

    Either layer degrades gracefully to "not found" if its data is missing —
    curated data always ships with the app, and the auto-detected layer is
    simply absent until the first successful background sync.
    """

    def __init__(
        self,
        cache: CacheClient,
        seed_path: Path = _SEED_PATH,
        coingecko: CoinGeckoClient | None = None,
        coingecko_timeout_seconds: float = 3.0,
    ) -> None:
        with open(seed_path, "r", encoding="utf-8") as fh:
            seed: dict[str, Any] = json.load(fh)

        self._tokens: dict[str, list[str]] = {
            ticker.upper(): data["bridges"] for ticker, data in seed["tokens"].items()
        }
        self._bridges: dict[str, dict[str, Any]] = seed["bridges"]
        self._cache = cache
        self._coingecko = coingecko
        self._coingecko_timeout = coingecko_timeout_seconds

    def bridge_keys(self) -> set[str]:
        return set(self._bridges.keys())

    def curated_bridge_keys_for(self, ticker: str) -> list[str] | None:
        """Raw curated lookup, bypassing the auto-detected layer — used by /debug."""
        return self._tokens.get(ticker.upper())

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
            auto_detected = await self._find_auto_detected(ticker)
            if auto_detected is not None:
                return auto_detected
            return await self._find_via_coingecko(ticker)

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
        index = await self._cache.get_token_index() or {}
        networks = sorted(index.get(ticker) or _MANUAL_NETWORK_FALLBACKS.get(ticker, []))
        return self._build_aggregator_results(networks)

    async def _find_via_coingecko(self, ticker: str) -> list[BridgeInfo] | None:
        if self._coingecko is None:
            return None

        networks = await self._cache.get_coingecko_networks(ticker)
        if networks is None:
            try:
                networks = await asyncio.wait_for(
                    self._coingecko.find_networks(ticker), timeout=self._coingecko_timeout
                )
            except Exception as exc:
                # Do NOT cache on failure (rate limit, timeout, network error, ...) —
                # caching here would freeze a transient error into a "confirmed not
                # found" result for the full cache TTL. Leaving it uncached means
                # the next query for this ticker retries live instead of trusting
                # a lookup that never actually completed.
                logger.warning("CoinGecko lookup failed for %s: %s", ticker, exc)
                await self._cache.set_coingecko_error(ticker, str(exc))
                return None
            await self._cache.set_coingecko_networks(ticker, networks)

        return self._build_aggregator_results(sorted(networks))

    def _build_aggregator_results(self, networks: list[str]) -> list[BridgeInfo] | None:
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
