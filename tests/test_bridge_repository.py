from app.services.bridge_repository import BridgeRepository


class DummyCache:
    async def get_bridge_chains(self, bridge_key: str):
        return None

    async def get_token_index(self):
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
        assert bridge.auto_detected is False


async def test_unknown_ticker_returns_none_when_no_live_index():
    repo = BridgeRepository(cache=DummyCache())

    assert await repo.find_bridges_for_ticker("NOT_A_REAL_TICKER") is None


async def test_suggestions_for_typo():
    repo = BridgeRepository(cache=DummyCache())

    suggestions = await repo.suggest_tickers("USDR")

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


async def test_auto_detected_layer_matches_uncurated_ticker_by_shared_networks():
    class IndexCache(DummyCache):
        async def get_token_index(self):
            return {"LSK": ["Ethereum", "Arbitrum"]}

    repo = BridgeRepository(cache=IndexCache())

    bridges = await repo.find_bridges_for_ticker("lsk")

    assert bridges is not None
    assert all(b.auto_detected for b in bridges)
    for bridge in bridges:
        assert set(bridge.networks) <= {"Ethereum", "Arbitrum"}
        assert len(bridge.networks) >= 2


async def test_auto_detected_layer_requires_at_least_two_shared_networks():
    class IndexCache(DummyCache):
        async def get_token_index(self):
            return {"LSK": ["Solana"]}

    repo = BridgeRepository(cache=IndexCache())

    assert await repo.find_bridges_for_ticker("LSK") is None


async def test_curated_ticker_takes_precedence_over_auto_detected_index():
    class IndexCache(DummyCache):
        async def get_token_index(self):
            return {"USDT": []}

    repo = BridgeRepository(cache=IndexCache())

    bridges = await repo.find_bridges_for_ticker("USDT")

    assert bridges is not None
    assert all(not b.auto_detected for b in bridges)


async def test_suggest_tickers_includes_live_index_tickers():
    class IndexCache(DummyCache):
        async def get_token_index(self):
            return {"LISK": ["Ethereum", "Arbitrum"]}

    repo = BridgeRepository(cache=IndexCache())

    suggestions = await repo.suggest_tickers("LISC")

    assert "LISK" in suggestions
