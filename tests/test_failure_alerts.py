from app.services.failure_alerts import FailureAlert


class RecordingNotifier:
    def __init__(self):
        self.messages: list[str] = []

    async def __call__(self, text: str) -> None:
        self.messages.append(text)


async def test_alerts_once_when_threshold_crossed_and_once_on_recovery():
    notifier = RecordingNotifier()
    alert = FailureAlert("Test Job", notifier, threshold=3)

    await alert.record_failure("boom 1")
    await alert.record_failure("boom 2")
    assert notifier.messages == []  # below threshold, no alert yet

    await alert.record_failure("boom 3")
    assert len(notifier.messages) == 1
    assert "Test Job" in notifier.messages[0]
    assert "boom 3" in notifier.messages[0]

    # Continuing to fail past the threshold must not spam more alerts.
    await alert.record_failure("boom 4")
    await alert.record_failure("boom 5")
    assert len(notifier.messages) == 1

    await alert.record_success()
    assert len(notifier.messages) == 2
    assert "снова работает" in notifier.messages[1]


async def test_no_alert_when_failures_never_cross_threshold():
    notifier = RecordingNotifier()
    alert = FailureAlert("Test Job", notifier, threshold=3)

    await alert.record_failure("boom 1")
    await alert.record_success()
    await alert.record_failure("boom 2")

    assert notifier.messages == []


async def test_success_after_no_failure_does_not_notify():
    notifier = RecordingNotifier()
    alert = FailureAlert("Test Job", notifier, threshold=3)

    await alert.record_success()
    await alert.record_success()

    assert notifier.messages == []


async def test_works_without_a_notifier():
    alert = FailureAlert("Test Job", None, threshold=1)

    # Must not raise even though there's nothing to call.
    await alert.record_failure("boom")
    await alert.record_success()
