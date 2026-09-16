from __future__ import annotations

from typing import Awaitable, Callable

NotifyFn = Callable[[str], Awaitable[None]]

_DEFAULT_THRESHOLD = 3


class FailureAlert:
    """Tracks consecutive failures of a background job and notifies once
    when the threshold is crossed, and once more on recovery.

    Without this, a background job that fails would either alert silently
    (nobody notices for days) or spam an alert on every single cycle it
    stays broken. Neither is useful — this notifies exactly on the two
    transitions that matter.
    """

    def __init__(self, name: str, notify: NotifyFn | None, threshold: int = _DEFAULT_THRESHOLD) -> None:
        self._name = name
        self._notify = notify
        self._threshold = threshold
        self._consecutive_failures = 0
        self._alerted = False

    async def record_failure(self, detail: str) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures == self._threshold and not self._alerted and self._notify is not None:
            self._alerted = True
            await self._notify(
                f"⚠️ <b>{self._name}</b> не смог обновить данные "
                f"{self._consecutive_failures} раз(а) подряд.\nПоследняя ошибка: {detail}"
            )

    async def record_success(self) -> None:
        if self._alerted and self._notify is not None:
            self._alerted = False
            await self._notify(f"✅ <b>{self._name}</b> снова работает нормально.")
        self._consecutive_failures = 0
