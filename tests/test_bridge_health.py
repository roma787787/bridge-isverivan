import app.services.bridge_health as bridge_health
from app.services.bridge_health import BridgeHealthChecker, _default_check_url

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


async def _no_op_sleep(seconds: float) -> None:
    pass


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


async def test_blocked_status_never_triggers_the_broken_alert():
    # A bridge that's always well-known and heavily used (Arbitrum Bridge,
    # Ronin Bridge in practice) returning 403/429 almost always means its WAF
    # is blocking our monitor, not that the site is actually down.
    cache = RecordingCache(initial={"a": "ok", "b": "ok"})
    notifier = RecordingNotifier()
    checker = BridgeHealthChecker(
        bridges=_BRIDGES,
        cache=cache,
        notify=notifier,
        interval_hours=24,
        timeout_seconds=10,
        check_url=_check_url_returning({"https://a.example": "ok", "https://b.example": "blocked_403"}),
    )

    await checker.check_once()

    assert notifier.messages == []
    assert cache.stored == {"a": "ok", "b": "blocked_403"}


async def test_blocked_status_on_first_run_does_not_alert():
    cache = RecordingCache(initial=None)
    notifier = RecordingNotifier()
    checker = BridgeHealthChecker(
        bridges=_BRIDGES,
        cache=cache,
        notify=notifier,
        interval_hours=24,
        timeout_seconds=10,
        check_url=_check_url_returning({"https://a.example": "blocked_429", "https://b.example": "ok"}),
    )

    await checker.check_once()

    assert notifier.messages == []


async def test_default_check_url_recovers_from_a_single_transient_failure(monkeypatch):
    # A dropped connection or DNS hiccup on the first attempt looks identical
    # to a real outage; retrying once tells a genuine outage (fails both
    # times) apart from a momentary blip (fails once, then succeeds) - this
    # is what a Blast Bridge "unreachable" alert turned out to be in practice.
    monkeypatch.setattr(bridge_health.asyncio, "sleep", _no_op_sleep)
    attempts = {"count": 0}

    async def flaky_get_status(url: str, timeout_seconds: float) -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ConnectionError("connection reset")
        return "ok"

    monkeypatch.setattr(bridge_health, "_get_status", flaky_get_status)

    status = await _default_check_url("https://example.com", 10)

    assert status == "ok"
    assert attempts["count"] == 2


async def test_default_check_url_reports_unreachable_after_both_attempts_fail(monkeypatch):
    monkeypatch.setattr(bridge_health.asyncio, "sleep", _no_op_sleep)

    async def always_failing_get_status(url: str, timeout_seconds: float) -> str:
        raise ConnectionError("connection reset")

    monkeypatch.setattr(bridge_health, "_get_status", always_failing_get_status)

    status = await _default_check_url("https://example.com", 10)

    assert status == "unreachable"


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
