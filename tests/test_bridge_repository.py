import asyncio

from app.services.bridge_repository import BridgeRepository


class DummyCache:
    async def get_bridge_chains(self, bridge_key: str):
        return None

    async def get_token_index(self):
        return None

    async def get_coingecko_networks(self, ticker: str):
        return None

    async def set_coingecko_networks(self, ticker: str, networks: list[str]) -> None:
        pass

    async def get_coingecko_error(self, ticker: str):
        return None

    async def set_coingecko_error(self, ticker: str, message: str) -> None:
        pass


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


async def test_manual_network_fallback_resolves_ticker_missing_from_live_index():
    # OP isn't in the curated dataset and Li.Fi's free feed doesn't reliably
    # list it on 2+ chains, so a hand-maintained fallback covers it.
    repo = BridgeRepository(cache=DummyCache())

    bridges = await repo.find_bridges_for_ticker("op")

    assert bridges is not None
    assert all(b.auto_detected for b in bridges)
    assert all(set(b.networks) == {"Ethereum", "Optimism"} for b in bridges)


async def test_manual_network_fallback_is_overridden_by_live_index_when_present():
    class IndexCache(DummyCache):
        async def get_token_index(self):
            return {"OP": ["Ethereum", "Optimism", "Base"]}

    repo = BridgeRepository(cache=IndexCache())

    bridges = await repo.find_bridges_for_ticker("OP")

    assert bridges is not None
    assert all("Base" in b.networks for b in bridges)


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
        "STRK": "Starknet",
        "FIL": "Filecoin",
    }
    for ticker, native_network in cases.items():
        bridges = await repo.find_bridges_for_ticker(ticker)
        assert bridges is not None, f"{ticker} should resolve to a curated bridge"
        assert any(native_network in b.networks for b in bridges), (
            f"{ticker} should list its native network {native_network!r}, got "
            f"{[b.networks for b in bridges]}"
        )
        assert all(not b.auto_detected for b in bridges)


async def test_solana_native_tokens_resolve_via_generic_wormhole_bridge():
    repo = BridgeRepository(cache=DummyCache())

    for ticker in ["JUP", "RAY", "BONK"]:
        bridges = await repo.find_bridges_for_ticker(ticker)
        assert bridges is not None, f"{ticker} should resolve via Wormhole"
        assert any(b.key == "wormhole" for b in bridges)
        assert any("Solana" in b.networks for b in bridges)


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


class RecordingCoingeckoCache(DummyCache):
    def __init__(self):
        self.stored: dict[str, list[str]] = {}
        self.errors: dict[str, str] = {}

    async def get_coingecko_networks(self, ticker: str):
        return self.stored.get(ticker)

    async def set_coingecko_networks(self, ticker: str, networks: list[str]) -> None:
        self.stored[ticker] = networks

    async def get_coingecko_error(self, ticker: str):
        return self.errors.get(ticker)

    async def set_coingecko_error(self, ticker: str, message: str) -> None:
        self.errors[ticker] = message


class FakeCoinGecko:
    def __init__(self, networks: list[str]):
        self.networks = networks
        self.call_count = 0

    async def find_networks(self, ticker: str) -> list[str]:
        self.call_count += 1
        return self.networks


async def test_coingecko_fallback_used_when_curated_and_live_index_miss():
    cache = RecordingCoingeckoCache()
    coingecko = FakeCoinGecko(["Ethereum", "Polygon"])
    repo = BridgeRepository(cache=cache, coingecko=coingecko)

    bridges = await repo.find_bridges_for_ticker("SOMENEWTOKEN")

    assert bridges is not None
    assert all(b.auto_detected for b in bridges)
    assert all(b.networks == ["Ethereum", "Polygon"] for b in bridges)
    assert coingecko.call_count == 1


async def test_coingecko_result_is_cached_and_not_requeried():
    cache = RecordingCoingeckoCache()
    coingecko = FakeCoinGecko(["Ethereum", "Polygon"])
    repo = BridgeRepository(cache=cache, coingecko=coingecko)

    await repo.find_bridges_for_ticker("SOMENEWTOKEN")
    await repo.find_bridges_for_ticker("SOMENEWTOKEN")

    assert coingecko.call_count == 1


async def test_coingecko_negative_result_is_cached_too():
    cache = RecordingCoingeckoCache()
    coingecko = FakeCoinGecko([])  # single-chain or unknown token
    repo = BridgeRepository(cache=cache, coingecko=coingecko)

    first = await repo.find_bridges_for_ticker("NOPETOKEN")
    second = await repo.find_bridges_for_ticker("NOPETOKEN")

    assert first is None
    assert second is None
    assert coingecko.call_count == 1
    assert cache.stored["NOPETOKEN"] == []


async def test_coingecko_lookup_failure_degrades_to_not_found_without_poisoning_cache():
    class FailingCoinGecko:
        def __init__(self):
            self.call_count = 0

        async def find_networks(self, ticker: str) -> list[str]:
            self.call_count += 1
            raise RuntimeError("429 rate limited")

    cache = RecordingCoingeckoCache()
    coingecko = FailingCoinGecko()
    repo = BridgeRepository(cache=cache, coingecko=coingecko)

    first = await repo.find_bridges_for_ticker("SOMENEWTOKEN")
    second = await repo.find_bridges_for_ticker("SOMENEWTOKEN")

    assert first is None
    assert second is None
    # A failed lookup must never be cached as a confirmed "not found" — every
    # call should retry live instead of trusting a lookup that never
    # actually completed.
    assert coingecko.call_count == 2
    assert "SOMENEWTOKEN" not in cache.stored
    assert "rate limited" in cache.errors["SOMENEWTOKEN"]


async def test_coingecko_lookup_times_out_gracefully_without_poisoning_cache():
    class SlowCoinGecko:
        async def find_networks(self, ticker: str) -> list[str]:
            await asyncio.sleep(1)
            return ["Ethereum", "Polygon"]

    cache = RecordingCoingeckoCache()
    repo = BridgeRepository(cache=cache, coingecko=SlowCoinGecko(), coingecko_timeout_seconds=0.05)

    result = await repo.find_bridges_for_ticker("SOMENEWTOKEN")

    assert result is None
    assert "SOMENEWTOKEN" not in cache.stored


async def test_no_coingecko_client_configured_returns_not_found():
    repo = BridgeRepository(cache=DummyCache())  # coingecko defaults to None

    assert await repo.find_bridges_for_ticker("SOMENEWTOKEN") is None


async def test_curated_and_live_index_take_precedence_over_coingecko():
    cache = RecordingCoingeckoCache()
    coingecko = FakeCoinGecko(["Ethereum", "Polygon"])
    repo = BridgeRepository(cache=cache, coingecko=coingecko)

    bridges = await repo.find_bridges_for_ticker("USDT")

    assert bridges is not None
    assert all(not b.auto_detected for b in bridges)
    assert coingecko.call_count == 0
