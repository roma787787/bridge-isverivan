from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from .bot.handlers import search as search_handlers
from .bot.handlers import start as start_handlers
from .bot.handlers import stats as stats_handlers
from .config import Settings
from .db.repository import Storage
from .services.bridge_repository import BridgeRepository
from .services.cache import CacheClient
from .services.defillama_client import DefiLlamaClient
from .services.sync import BridgeSyncService

logger = logging.getLogger(__name__)


async def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    storage = Storage(settings.database_path)
    await storage.connect()

    cache_ttl = int(settings.sync_interval_hours * 3600 * 1.5)
    cache = CacheClient(settings.redis_url, ttl_seconds=cache_ttl)
    bridge_repository = BridgeRepository(cache=cache)

    defillama_client = DefiLlamaClient(settings.defillama_base_url, settings.request_timeout_seconds)
    sync_service = BridgeSyncService(
        client=defillama_client,
        cache=cache,
        seed_bridge_keys=bridge_repository.bridge_keys(),
        interval_hours=settings.sync_interval_hours,
    )

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(start_handlers.router)
    dp.include_router(stats_handlers.router)
    dp.include_router(search_handlers.router)

    sync_task = asyncio.create_task(sync_service.run_forever())

    try:
        await dp.start_polling(
            bot,
            bridge_repository=bridge_repository,
            storage=storage,
            settings=settings,
        )
    finally:
        sync_task.cancel()
        await cache.close()
        await storage.close()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
