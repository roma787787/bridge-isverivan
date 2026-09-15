from app.services.bridge_repository import BridgeRepository


class DummyCache:
    async def get_bridge_chains(self, bridge_key: str):
        return None

    async def get_token_index(self):
        return None


def test_curated_bridge_keys_for_reports_raw_curated_lookup():
    repo = BridgeRepository(cache=DummyCache())

    assert repo.curated_bridge_keys_for("usdt") == repo.curated_bridge_keys_for("USDT")
    assert repo.curated_bridge_keys_for("USDT")
    assert repo.curated_bridge_keys_for("NOT_A_REAL_TICKER") is None


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


async def test_auto_detected_layer_returns_general_aggregators_for_uncurated_ticker():
    class IndexCache(DummyCache):
        async def get_token_index(self):
            return {"LSK": ["Ethereum", "Arbitrum"]}

    repo = BridgeRepository(cache=IndexCache())

    bridges = await repo.find_bridges_for_ticker("lsk")

    assert bridges is not None
    assert len(bridges) == 4  # the fixed list of general-purpose aggregators
    assert all(b.auto_detected for b in bridges)
    for bridge in bridges:
        assert bridge.networks == ["Arbitrum", "Ethereum"]
        assert bridge.url.startswith("https://")


async def test_auto_detected_layer_requires_at_least_two_networks():
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


async def test_native_non_evm_chain_tickers_are_curated_with_their_own_network():
    repo = BridgeRepository(cache=DummyCache())

    cases = {
        "TON": "TON",
        "BTC": "Bitcoin",
        "ATOM": "Cosmos Hub",
        "DOT": "Polkadot",
        "NEAR": "NEAR",
    }
    for ticker, native_network in cases.items():
        bridges = await repo.find_bridges_for_ticker(ticker)
        assert bridges is not None, f"{ticker} should resolve to a curated bridge"
        assert any(native_network in b.networks for b in bridges), (
            f"{ticker} should list its native network {native_network!r}, got "
            f"{[b.networks for b in bridges]}"
        )
        assert all(not b.auto_detected for b in bridges)


async def test_thin_curated_entry_is_supplemented_with_extra_auto_detected_networks():
    class IndexCache(DummyCache):
        async def get_token_index(self):
            # TON's curated entry only covers TON/Ethereum/BNB Chain; the
            # live index also found a wrapped version on Gnosis.
            return {"TON": ["BNB Chain", "Ethereum", "Gnosis"]}

    repo = BridgeRepository(cache=IndexCache())

    bridges = await repo.find_bridges_for_ticker("TON")

    assert bridges is not None
    curated = [b for b in bridges if not b.auto_detected]
    auto = [b for b in bridges if b.auto_detected]
    assert len(curated) == 1
    assert curated[0].key == "tonbridge"
    assert "TON" in curated[0].networks
    assert len(auto) == 4  # supplemented with the general aggregators
    assert all("Gnosis" in b.networks for b in auto)


async def test_thin_curated_entry_is_not_supplemented_when_no_new_networks():
    class IndexCache(DummyCache):
        async def get_token_index(self):
            # Same networks the curated TON bridge already reports.
            return {"TON": ["BNB Chain", "Ethereum"]}

    repo = BridgeRepository(cache=IndexCache())

    bridges = await repo.find_bridges_for_ticker("TON")

    assert bridges is not None
    assert all(not b.auto_detected for b in bridges)


async def test_well_covered_curated_ticker_is_not_supplemented():
    class IndexCache(DummyCache):
        async def get_token_index(self):
            return {"USDT": ["Ethereum", "SomeBrandNewChain"]}

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
