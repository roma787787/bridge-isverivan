from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

import httpx

from .cache import CacheClient
from .failure_alerts import NotifyFn

logger = logging.getLogger(__name__)

_MAX_CONCURRENT_CHECKS = 10
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    # Some dApp frontends (Boba Network Hub's http_500 was confirmed a false
    # positive - the same page loads fine in a real browser) run edge
    # middleware that behaves differently for requests missing these
    # standard browser fetch-metadata/hint headers, treating them as
    # non-browser traffic even with a convincing User-Agent.
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

# Bridge frontends are frequently sat behind Cloudflare/Vercel-style bot
# protection that returns one of these for *any* non-browser client,
# monitoring services included — it says nothing about whether the site is
# actually up for a real visitor. Treating these as "broken" produced
# false-positive alerts in practice (Arbitrum Bridge and Ronin Bridge, two
# of the most heavily used bridges in the space, both "403"; Berachain
# Bridge "429" — a 429 by definition means the server is up and responding).
# These are recorded and visible, but never drive the urgent "mosты сломаны"
# alert on their own.
_BLOCKED_STATUS_CODES = {401, 403, 429}

CheckUrlFn = Callable[[str], Awaitable[str]]


_RETRY_DELAY_SECONDS = 3


async def _get_status(url: str, timeout_seconds: float) -> str:
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
        response = await client.get(url, headers=_HEADERS)
    if response.status_code < 400:
        return "ok"
    if response.status_code in _BLOCKED_STATUS_CODES:
        return f"blocked_{response.status_code}"
    return f"http_{response.status_code}"


async def _attempt_status(url: str, timeout_seconds: float) -> str:
    try:
        return await _get_status(url, timeout_seconds)
    except Exception as exc:
        logger.warning("Health check attempt failed for %s: %s", url, exc)
        return "unreachable"


def _should_retry(status: str) -> bool:
    return status == "unreachable" or status.startswith("http_5")


async def _default_check_url(url: str, timeout_seconds: float) -> str:
    # A dropped connection and a 5xx response can both mean a genuine outage
    # or just a momentary blip (a deploy in progress, an upstream timeout, a
    # CDN that couldn't complete the TLS handshake with its own origin) -
    # both looked identical to a real Boba Network/Canto outage in practice
    # (500 and 525 respectively) right after those bridges were added. One
    # retry after a short pause tells a blip apart from a bridge that's
    # actually down, which will still fail the same way on the retry.
    status = await _attempt_status(url, timeout_seconds)
    if _should_retry(status):
        await asyncio.sleep(_RETRY_DELAY_SECONDS)
        status = await _attempt_status(url, timeout_seconds)
    return status


def _is_broken(status: str) -> bool:
    return status != "ok" and not status.startswith("blocked_")


class BridgeHealthChecker:
    """Periodically checks that every curated bridge/aggregator URL is still reachable.

    Bridges occasionally disappear or change domains without warning (the
    dYdX Ethereum<->Chain bridge, discontinued by governance, is a real
    example found during testing). Rather than waiting for a user to report
    a dead link, this pings each curated URL on a schedule and notifies the
    admin only when a bridge's reachability *changes* — healthy -> broken or
    broken -> healthy — so a bridge that's been down for a week doesn't
    re-alert every cycle. Statuses that just mean "this looks like a bot to
    the site's WAF" (401/403/429) are tracked but never trigger the urgent
    alert on their own — see ``_BLOCKED_STATUS_CODES``.
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
            key
            for key, status in new_status.items()
            if _is_broken(status) and not _is_broken(previous_status.get(key, "ok"))
        ]
        recovered = [
            key
            for key, status in new_status.items()
            if not _is_broken(status) and _is_broken(previous_status.get(key, "ok"))
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
