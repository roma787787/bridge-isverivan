from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from .bot.handlers import debug as debug_handlers
from .bot.handlers import search as search_handlers
from .bot.handlers import start as start_handlers
from .bot.handlers import stats as stats_handlers
from .config import Settings
from .db.repository import Storage
from .services.bridge_repository import BridgeRepository
from .services.cache import CacheClient
from .services.coingecko_client import CoinGeckoClient
from .services.defillama_client import DefiLlamaClient
from .services.lifi_client import LiFiClient
from .services.sync import BridgeSyncService
from .services.token_sync import TokenIndexSyncService

logger = logging.getLogger(__name__)


async def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    storage = Storage(settings.database_path)
    await storage.connect()

    cache_ttl = int(settings.sync_interval_hours * 3600 * 1.5)
    cache = CacheClient(settings.redis_url, ttl_seconds=cache_ttl)
    coingecko_client = CoinGeckoClient(settings.coingecko_base_url, settings.coingecko_timeout_seconds)
    bridge_repository = BridgeRepository(
        cache=cache,
        coingecko=coingecko_client,
        coingecko_timeout_seconds=settings.coingecko_timeout_seconds,
    )

    defillama_client = DefiLlamaClient(settings.defillama_base_url, settings.request_timeout_seconds)
    sync_service = BridgeSyncService(
        client=defillama_client,
        cache=cache,
        seed_bridge_keys=bridge_repository.bridge_keys(),
        interval_hours=settings.sync_interval_hours,
    )

    lifi_client = LiFiClient(settings.lifi_base_url, settings.lifi_sync_timeout_seconds)
    token_index_sync_service = TokenIndexSyncService(
        client=lifi_client,
        cache=cache,
        interval_hours=settings.sync_interval_hours,
    )

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(start_handlers.router)
    dp.include_router(stats_handlers.router)
    dp.include_router(debug_handlers.router)
    dp.include_router(search_handlers.router)

    sync_task = asyncio.create_task(sync_service.run_forever())
    token_index_sync_task = asyncio.create_task(token_index_sync_service.run_forever())

    try:
        await dp.start_polling(
            bot,
            bridge_repository=bridge_repository,
            storage=storage,
            settings=settings,
            cache=cache,
        )
    finally:
        sync_task.cancel()
        token_index_sync_task.cancel()
        await cache.close()
        await storage.close()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
