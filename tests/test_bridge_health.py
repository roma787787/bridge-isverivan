from app.services.bridge_health import BridgeHealthChecker

_BRIDGES = {
    "a": {"display_name": "Bridge A", "url": "https://a.example"},
    "b": {"display_name": "Bridge B", "url": "https://b.example"},
}


class RecordingCache:
    def __init__(self, initial: dict[str, str] | None = None):
        self.stored = initial

    async def get_bridge_health(self):
        return self.stored

    async def set_bridge_health(self, health):
        self.stored = health


class RecordingNotifier:
    def __init__(self):
        self.messages: list[str] = []

    async def __call__(self, text: str) -> None:
        self.messages.append(text)


def _check_url_returning(statuses: dict[str, str]):
    async def check(url: str) -> str:
        return statuses[url]

    return check


async def test_first_run_alerts_for_already_broken_bridges():
    cache = RecordingCache(initial=None)
    notifier = RecordingNotifier()
    checker = BridgeHealthChecker(
        bridges=_BRIDGES,
        cache=cache,
        notify=notifier,
        interval_hours=24,
        timeout_seconds=10,
        check_url=_check_url_returning({"https://a.example": "ok", "https://b.example": "unreachable"}),
    )

    await checker.check_once()

    assert len(notifier.messages) == 1
    assert "Bridge B" in notifier.messages[0]
    assert "Bridge A" not in notifier.messages[0]
    assert cache.stored == {"a": "ok", "b": "unreachable"}


async def test_first_run_with_everything_healthy_sends_no_alert():
    cache = RecordingCache(initial=None)
    notifier = RecordingNotifier()
    checker = BridgeHealthChecker(
        bridges=_BRIDGES,
        cache=cache,
        notify=notifier,
        interval_hours=24,
        timeout_seconds=10,
        check_url=_check_url_returning({"https://a.example": "ok", "https://b.example": "ok"}),
    )

    await checker.check_once()

    assert notifier.messages == []


async def test_staying_broken_does_not_re_alert():
    cache = RecordingCache(initial={"a": "ok", "b": "unreachable"})
    notifier = RecordingNotifier()
    checker = BridgeHealthChecker(
        bridges=_BRIDGES,
        cache=cache,
        notify=notifier,
        interval_hours=24,
        timeout_seconds=10,
        check_url=_check_url_returning({"https://a.example": "ok", "https://b.example": "unreachable"}),
    )

    await checker.check_once()

    assert notifier.messages == []  # already known broken, no new alert


async def test_recovery_is_reported():
    cache = RecordingCache(initial={"a": "ok", "b": "unreachable"})
    notifier = RecordingNotifier()
    checker = BridgeHealthChecker(
        bridges=_BRIDGES,
        cache=cache,
        notify=notifier,
        interval_hours=24,
        timeout_seconds=10,
        check_url=_check_url_returning({"https://a.example": "ok", "https://b.example": "ok"}),
    )

    await checker.check_once()

    assert len(notifier.messages) == 1
    assert "снова доступны" in notifier.messages[0]
    assert "Bridge B" in notifier.messages[0]


async def test_transition_to_broken_is_reported():
    cache = RecordingCache(initial={"a": "ok", "b": "ok"})
    notifier = RecordingNotifier()
    checker = BridgeHealthChecker(
        bridges=_BRIDGES,
        cache=cache,
        notify=notifier,
        interval_hours=24,
        timeout_seconds=10,
        check_url=_check_url_returning({"https://a.example": "ok", "https://b.example": "http_404"}),
    )

    await checker.check_once()

    assert len(notifier.messages) == 1
    assert "Проблемы" in notifier.messages[0]
    assert "Bridge B" in notifier.messages[0]


async def test_no_notifier_does_not_crash():
    cache = RecordingCache(initial=None)
    checker = BridgeHealthChecker(
        bridges=_BRIDGES,
        cache=cache,
        notify=None,
        interval_hours=24,
        timeout_seconds=10,
        check_url=_check_url_returning({"https://a.example": "unreachable", "https://b.example": "ok"}),
    )

    await checker.check_once()  # must not raise

    assert cache.stored == {"a": "unreachable", "b": "ok"}
