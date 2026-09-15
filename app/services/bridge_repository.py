from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cache import CacheClient

_SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "bridges_seed.json"


@dataclass(frozen=True)
class BridgeInfo:
    key: str
    display_name: str
    url: str
    networks: list[str]


class BridgeRepository:
    """Resolves which bridges support a given token ticker.

    The bundled ``bridges_seed.json`` is a curated reference dataset mapping
    tickers to bridges and each bridge's official site. It is not fetched
    live because the free DefiLlama Bridges endpoint reports bridges and the
    chains they operate on, not which specific tokens they support, and a
    fully live per-token lookup requires a paid/aggregator API. Instead, the
    periodic sync job (see ``services.sync``) refreshes each bridge's chain
    list from DefiLlama so the "supported networks" shown to users stays
    current even though the token-to-bridge mapping itself is curated.
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
        bridge_keys = self._tokens.get(ticker.upper())
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

    def suggest_tickers(self, raw: str, limit: int = 3) -> list[str]:
        return difflib.get_close_matches(raw.upper(), self.all_known_tickers(), n=limit, cutoff=0.5)
