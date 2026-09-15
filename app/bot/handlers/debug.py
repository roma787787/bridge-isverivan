from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ...config import Settings
from ...services.bridge_repository import BridgeRepository
from ...services.cache import CacheClient

router = Router(name="debug")


@router.message(Command("debug"))
async def handle_debug(
    message: Message,
    command: CommandObject,
    bridge_repository: BridgeRepository,
    cache: CacheClient,
    settings: Settings,
) -> None:
    if message.from_user is None or message.from_user.id not in settings.admin_ids:
        return

    ticker = (command.args or "").strip().upper()
    if not ticker:
        await message.answer("Использование: <code>/debug TICKER</code>, например <code>/debug OP</code>")
        return

    lines = [f"\U0001f50d <b>Диагностика для {escape(ticker)}</b>", ""]

    curated_keys = bridge_repository.curated_bridge_keys_for(ticker)
    if curated_keys:
        lines.append(f"✅ В курируемом списке: {escape(', '.join(curated_keys))}")
    else:
        lines.append("❌ В курируемом списке нет")

    index = await cache.get_token_index()
    live_networks = index.get(ticker) if index else None
    if live_networks:
        lines.append(f"✅ В live-индексе Li.Fi: {escape(', '.join(live_networks))}")
    else:
        lines.append("❌ В live-индексе Li.Fi нет (или существует меньше чем на 2 сетях)")

    meta = await cache.get_token_index_meta()
    lines.append("")
    if meta:
        lines.append(f"Последняя синхронизация индекса: {escape(str(meta.get('updated_at', '—')))}")
        lines.append(f"Сетей запрошено у Li.Fi: {meta.get('chain_count', '—')}")
        lines.append(f"Сетей, где Li.Fi вернул хотя бы один токен: {meta.get('chains_with_tokens', '—')}")
        lines.append(f"Всего тикеров в индексе (2+ сети): {meta.get('ticker_count', '—')}")
    else:
        lines.append("⚠️ Индекс Li.Fi ещё ни разу успешно не синхронизировался.")

    await message.answer("\n".join(lines))
