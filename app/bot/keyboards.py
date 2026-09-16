from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..services.bridge_repository import BridgeInfo


def build_bridges_keyboard(bridges: list[BridgeInfo]) -> InlineKeyboardMarkup:
    """One tappable button per bridge, opening its site directly."""
    rows = [[InlineKeyboardButton(text=f"{bridge.display_name} ↗", url=bridge.url)] for bridge in bridges]
    return InlineKeyboardMarkup(inline_keyboard=rows)
