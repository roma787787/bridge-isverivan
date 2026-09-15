from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cache import CacheClient

_SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "bridges_seed.json"
_MIN_SHARED_NETWORKS_FOR_AUTO_MATCH = 2


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
       Li.Fi token list: any ticker that exists on 2+ chains we track is
       matched against our curated bridges by intersecting the token's
       chains with each bridge's currently known chains. This is a heuristic
       (it assumes a general-purpose bridge operating on both chains can
       likely route the token), so results from this layer are flagged via
       ``BridgeInfo.auto_detected`` and the bot tells the user to double
       check the exact route on the bridge's own site.

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
        if curated is not None:
            return curated

        return await self._find_auto_detected(ticker)

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

        token_networks = set(index.get(ticker, []))
        if not token_networks:
            return None

        result: list[BridgeInfo] = []
        for key, bridge in self._bridges.items():
            bridge_networks = set(await self._networks_for(key))
            shared = sorted(bridge_networks & token_networks)
            if len(shared) >= _MIN_SHARED_NETWORKS_FOR_AUTO_MATCH:
                result.append(
                    BridgeInfo(
                        key=key,
                        display_name=bridge["display_name"],
                        url=bridge["url"],
                        networks=shared,
                        auto_detected=True,
                    )
                )
        return result or None

    async def suggest_tickers(self, raw: str, limit: int = 3) -> list[str]:
        known = set(self.all_known_tickers())
        index = await self._cache.get_token_index()
        if index:
            known |= set(index.keys())
        return difflib.get_close_matches(raw.upper(), known, n=limit, cutoff=0.5)
