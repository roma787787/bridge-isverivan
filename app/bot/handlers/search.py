from __future__ import annotations

import re

from aiogram import Router
from aiogram.types import Message

from ...db.repository import Storage
from ...services.bridge_repository import BridgeRepository
from ..formatting import format_bridges_message, format_invalid_input_message, format_not_found_message

router = Router(name="search")

_TICKER_RE = re.compile(r"^\$?[A-Za-z0-9]{2,15}$")


def _looks_like_plain_text(message: Message) -> bool:
    return bool(message.text) and not message.text.startswith("/")


@router.message(_looks_like_plain_text)
async def handle_ticker(message: Message, bridge_repository: BridgeRepository, storage: Storage) -> None:
    if message.from_user is None:
        return

    raw = message.text.strip()
    await storage.touch_user(message.from_user.id, message.from_user.username)

    if not raw or not _TICKER_RE.match(raw):
        await message.answer(format_invalid_input_message())
        return

    ticker = raw.lstrip("$").upper()
    bridges = await bridge_repository.find_bridges_for_ticker(ticker)

    if bridges:
        await storage.log_query(message.from_user.id, ticker, matched=True)
        await message.answer(format_bridges_message(ticker, bridges), disable_web_page_preview=True)
        return

    await storage.log_query(message.from_user.id, ticker, matched=False)
    suggestions = await bridge_repository.suggest_tickers(ticker)
    await message.answer(format_not_found_message(ticker, suggestions))
