from app.services.sync import BridgeSyncService


class FakeClient:
    def __init__(self, bridges):
        self._bridges = bridges

    async def fetch_bridges(self):
        return self._bridges


class RecordingCache:
    def __init__(self):
        self.stored: dict[str, list[str]] = {}

    async def set_bridge_chains(self, bridge_key, chains):
        self.stored[bridge_key] = chains


async def test_sync_once_stores_matching_bridges_by_name():
    client = FakeClient(
        [
            {"name": "Stargate", "chains": ["Ethereum", "Arbitrum", "Base"]},
            {"displayName": "Unrelated Bridge", "chains": ["Somechain"]},
        ]
    )
    cache = RecordingCache()
    service = BridgeSyncService(client=client, cache=cache, seed_bridge_keys={"stargate", "hop"}, interval_hours=8)

    await service.sync_once()

    assert cache.stored == {"stargate": ["Ethereum", "Arbitrum", "Base"]}


async def test_sync_once_survives_client_failure():
    class FailingClient:
        async def fetch_bridges(self):
            raise RuntimeError("network down")

    cache = RecordingCache()
    service = BridgeSyncService(client=FailingClient(), cache=cache, seed_bridge_keys={"stargate"}, interval_hours=8)

    await service.sync_once()

    assert cache.stored == {}


async def test_sync_once_notifies_after_repeated_failures_and_on_recovery():
    class FailingClient:
        async def fetch_bridges(self):
            raise RuntimeError("network down")

    messages: list[str] = []

    async def notify(text: str) -> None:
        messages.append(text)

    cache = RecordingCache()
    service = BridgeSyncService(
        client=FailingClient(), cache=cache, seed_bridge_keys={"stargate"}, interval_hours=8, notify=notify
    )

    await service.sync_once()
    await service.sync_once()
    assert messages == []  # below the default threshold of 3

    await service.sync_once()
    assert len(messages) == 1

    working_client = FakeClient([{"name": "Stargate", "chains": ["Ethereum"]}])
    service._client = working_client
    await service.sync_once()

    assert len(messages) == 2
    assert "снова работает" in messages[1]
