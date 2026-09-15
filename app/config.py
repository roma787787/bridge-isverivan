from __future__ import annotations

import os
from dataclasses import dataclass


def _parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: set[int]
    redis_url: str
    database_path: str
    defillama_base_url: str
    lifi_base_url: str
    sync_interval_hours: float
    request_timeout_seconds: float
    lifi_sync_timeout_seconds: float
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        bot_token = os.environ.get("BOT_TOKEN", "").strip()
        if not bot_token:
            raise RuntimeError("BOT_TOKEN environment variable is required")

        return cls(
            bot_token=bot_token,
            admin_ids=_parse_admin_ids(os.environ.get("ADMIN_IDS", "")),
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            database_path=os.environ.get("DATABASE_PATH", "data/bridgefinder.db"),
            defillama_base_url=os.environ.get("DEFILLAMA_BASE_URL", "https://bridges.llama.fi"),
            lifi_base_url=os.environ.get("LIFI_BASE_URL", "https://li.quest"),
            sync_interval_hours=float(os.environ.get("SYNC_INTERVAL_HOURS", "8")),
            request_timeout_seconds=float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "5")),
            lifi_sync_timeout_seconds=float(os.environ.get("LIFI_SYNC_TIMEOUT_SECONDS", "30")),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
