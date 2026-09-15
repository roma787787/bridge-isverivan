from __future__ import annotations

import asyncio
import logging

from .cache import CacheClient
from .defillama_client import DefiLlamaClient

logger = logging.getLogger(__name__)


class BridgeSyncService:
    """Periodically refreshes bridge chain lists from DefiLlama into the cache."""

    def __init__(
        self,
        client: DefiLlamaClient,
        cache: CacheClient,
        seed_bridge_keys: set[str],
        interval_hours: float,
    ) -> None:
        self._client = client
        self._cache = cache
        self._seed_keys = seed_bridge_keys
        self._interval_seconds = interval_hours * 3600

    async def sync_once(self) -> None:
        try:
            bridges = await self._client.fetch_bridges()
        except Exception as exc:
            logger.warning("DefiLlama bridge sync failed, keeping previous data: %s", exc)
            return

        chains_by_name: dict[str, list[str]] = {}
        for bridge in bridges:
            name = str(bridge.get("name") or bridge.get("displayName") or "").strip().lower()
            chains = bridge.get("chains") or []
            if name and chains:
                chains_by_name[name] = chains

        updated = 0
        for key in self._seed_keys:
            chains = chains_by_name.get(key)
            if chains:
                await self._cache.set_bridge_chains(key, chains)
                updated += 1

        logger.info("Bridge sync complete: refreshed %d/%d bridges from DefiLlama", updated, len(self._seed_keys))

    async def run_forever(self) -> None:
        while True:
            await self.sync_once()
            await asyncio.sleep(self._interval_seconds)
