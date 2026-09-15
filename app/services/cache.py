from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


class CacheClient:
    """Redis-backed cache with a transparent in-memory fallback.

    If Redis is unreachable (down, wrong URL, network hiccup) the bot keeps
    working: reads/writes fall back to an in-process dict so a single node
    stays responsive, at the cost of losing the cache on restart.
    """

    def __init__(self, redis_url: str, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._memory: dict[str, str] = {}
        self._redis = None
        try:
            import redis.asyncio as redis_asyncio

            self._redis = redis_asyncio.from_url(redis_url, decode_responses=True)
        except Exception as exc:  # pragma: no cover - depends on optional dependency/env
            logger.warning("Redis client could not be initialized (%s); using in-memory cache only", exc)

    async def get_bridge_chains(self, bridge_key: str) -> list[str] | None:
        raw = await self._get(f"bridge:chains:{bridge_key}")
        return json.loads(raw) if raw else None

    async def set_bridge_chains(self, bridge_key: str, chains: list[str]) -> None:
        await self._set(f"bridge:chains:{bridge_key}", json.dumps(chains))

    async def get_token_index(self) -> dict[str, list[str]] | None:
        raw = await self._get("token:index")
        return json.loads(raw) if raw else None

    async def set_token_index(self, index: dict[str, list[str]]) -> None:
        await self._set("token:index", json.dumps(index))

    async def get_token_index_meta(self) -> dict | None:
        raw = await self._get("token:index:meta")
        return json.loads(raw) if raw else None

    async def set_token_index_meta(self, meta: dict) -> None:
        await self._set("token:index:meta", json.dumps(meta))

    async def get_coingecko_networks(self, ticker: str) -> list[str] | None:
        """Returns None when never looked up; [] means "looked up, found nothing"."""
        raw = await self._get(f"coingecko:{ticker}")
        return json.loads(raw) if raw else None

    async def set_coingecko_networks(self, ticker: str, networks: list[str]) -> None:
        await self._set(f"coingecko:{ticker}", json.dumps(networks))

    async def get_coingecko_error(self, ticker: str) -> str | None:
        """Last error message for a ticker whose lookup never completed successfully."""
        return await self._get(f"coingecko:error:{ticker}")

    async def set_coingecko_error(self, ticker: str, message: str) -> None:
        await self._set(f"coingecko:error:{ticker}", message)

    async def _get(self, key: str) -> str | None:
        if self._redis is not None:
            try:
                return await self._redis.get(key)
            except Exception as exc:
                logger.warning("Redis GET failed (%s); falling back to memory cache", exc)
        return self._memory.get(key)

    async def _set(self, key: str, value: str) -> None:
        if self._redis is not None:
            try:
                await self._redis.set(key, value, ex=self._ttl)
                return
            except Exception as exc:
                logger.warning("Redis SET failed (%s); falling back to memory cache", exc)
        self._memory[key] = value

    async def close(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:  # pragma: no cover - best-effort cleanup
                pass
