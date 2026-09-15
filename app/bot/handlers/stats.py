from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ...config import Settings
from ...db.repository import Storage

router = Router(name="stats")


@router.message(Command("stats"))
async def handle_stats(message: Message, storage: Storage, settings: Settings) -> None:
    if message.from_user is None or message.from_user.id not in settings.admin_ids:
        return

    stats = await storage.get_stats()
    top_today = "\n".join(f"  • {ticker} — {count}" for ticker, count in stats.top_today) or "  • нет данных"
    top_month = "\n".join(f"  • {ticker} — {count}" for ticker, count in stats.top_month) or "  • нет данных"

    text = (
        "\U0001f4ca <b>Статистика BridgeFinder</b>\n\n"
        f"\U0001f465 Уникальных пользователей: <b>{stats.total_users}</b>\n"
        f"\U0001f4e8 Запросов сегодня: <b>{stats.queries_today}</b>\n"
        f"\U0001f4e8 Запросов за месяц: <b>{stats.queries_month}</b>\n\n"
        f"\U0001f525 Популярные тикеры сегодня:\n{top_today}\n\n"
        f"\U0001f525 Популярные тикеры за месяц:\n{top_month}"
    )
    await message.answer(text)
