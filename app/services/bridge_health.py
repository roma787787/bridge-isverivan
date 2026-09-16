from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

import httpx

from .cache import CacheClient
from .failure_alerts import NotifyFn

logger = logging.getLogger(__name__)

_MAX_CONCURRENT_CHECKS = 10
_USER_AGENT = "Mozilla/5.0 (compatible; BridgeFinderBot/1.0)"

CheckUrlFn = Callable[[str], Awaitable[str]]


async def _default_check_url(url: str, timeout_seconds: float) -> str:
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": _USER_AGENT})
        if response.status_code < 400:
            return "ok"
        return f"http_{response.status_code}"
    except Exception as exc:
        logger.warning("Health check failed for %s: %s", url, exc)
        return "unreachable"


class BridgeHealthChecker:
    """Periodically checks that every curated bridge/aggregator URL is still reachable.

    Bridges occasionally disappear or change domains without warning (the
    dYdX Ethereum<->Chain bridge, discontinued by governance, is a real
    example found during testing). Rather than waiting for a user to report
    a dead link, this pings each curated URL on a schedule and notifies the
    admin only when a bridge's reachability *changes* — healthy -> broken or
    broken -> healthy — so a bridge that's been down for a week doesn't
    re-alert every cycle.
    """

    def __init__(
        self,
        bridges: dict[str, dict[str, str]],
        cache: CacheClient,
        notify: NotifyFn | None,
        interval_hours: float,
        timeout_seconds: float,
        check_url: CheckUrlFn | None = None,
    ) -> None:
        self._bridges = bridges
        self._cache = cache
        self._notify = notify
        self._interval_seconds = interval_hours * 3600
        self._timeout = timeout_seconds
        self._check_url = check_url or (lambda url: _default_check_url(url, self._timeout))

    async def check_once(self) -> None:
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_CHECKS)

        async def check(key: str, url: str) -> tuple[str, str]:
            async with semaphore:
                return key, await self._check_url(url)

        results = await asyncio.gather(*(check(key, bridge["url"]) for key, bridge in self._bridges.items()))
        new_status = dict(results)

        previous_status = await self._cache.get_bridge_health() or {}
        await self._cache.set_bridge_health(new_status)

        newly_broken = [
            key for key, status in new_status.items() if status != "ok" and previous_status.get(key, "ok") == "ok"
        ]
        recovered = [
            key for key, status in new_status.items() if status == "ok" and previous_status.get(key, "ok") != "ok"
        ]

        logger.info(
            "Bridge health check complete: %d checked, %d newly broken, %d recovered",
            len(new_status),
            len(newly_broken),
            len(recovered),
        )

        if self._notify is None:
            return

        if newly_broken:
            lines = ["⚠️ <b>Проблемы с мостами</b>", ""]
            for key in newly_broken:
                bridge = self._bridges[key]
                lines.append(f"• {bridge['display_name']} ({new_status[key]}): {bridge['url']}")
            await self._notify("\n".join(lines))

        if recovered:
            lines = ["✅ <b>Мосты снова доступны</b>", ""]
            for key in recovered:
                bridge = self._bridges[key]
                lines.append(f"• {bridge['display_name']}: {bridge['url']}")
            await self._notify("\n".join(lines))

    async def run_forever(self) -> None:
        while True:
            try:
                await self.check_once()
            except Exception as exc:
                logger.warning("Bridge health check cycle failed: %s", exc)
            await asyncio.sleep(self._interval_seconds)
