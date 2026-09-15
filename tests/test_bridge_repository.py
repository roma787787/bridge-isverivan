from app.services.bridge_repository import BridgeRepository


class DummyCache:
    async def get_bridge_chains(self, bridge_key: str):
        return None


async def test_find_bridges_is_case_insensitive():
    repo = BridgeRepository(cache=DummyCache())

    upper = await repo.find_bridges_for_ticker("USDT")
    lower = await repo.find_bridges_for_ticker("usdt")
    mixed = await repo.find_bridges_for_ticker("Usdt")

    assert upper is not None
    assert [b.key for b in upper] == [b.key for b in lower] == [b.key for b in mixed]


async def test_find_bridges_returns_networks_and_urls():
    repo = BridgeRepository(cache=DummyCache())

    bridges = await repo.find_bridges_for_ticker("ETH")

    assert bridges is not None
    assert len(bridges) > 0
    for bridge in bridges:
        assert bridge.display_name
        assert bridge.url.startswith("https://")
        assert len(bridge.networks) > 0


async def test_unknown_ticker_returns_none():
    repo = BridgeRepository(cache=DummyCache())

    assert await repo.find_bridges_for_ticker("NOT_A_REAL_TICKER") is None


def test_suggestions_for_typo():
    repo = BridgeRepository(cache=DummyCache())

    suggestions = repo.suggest_tickers("USDR")

    assert set(suggestions) & {"USDT", "USDC"}


async def test_live_cache_data_is_merged_into_networks():
    class LiveCache(DummyCache):
        async def get_bridge_chains(self, bridge_key: str):
            if bridge_key == "stargate":
                return ["Ethereum", "Some New Chain"]
            return None

    repo = BridgeRepository(cache=LiveCache())
    bridges = await repo.find_bridges_for_ticker("USDT")

    stargate = next(b for b in bridges if b.key == "stargate")
    assert "Some New Chain" in stargate.networks
