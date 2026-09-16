from app.services.token_sync import TokenIndexSyncService


class FakeLiFiClient:
    def __init__(self, chains, tokens_by_chain):
        self._chains = chains
        self._tokens_by_chain = tokens_by_chain

    async def fetch_chains(self):
        return self._chains

    async def fetch_tokens_by_chain(self, chain_ids):
        return {chain_id: self._tokens_by_chain.get(chain_id, []) for chain_id in chain_ids}


class RecordingCache:
    def __init__(self):
        self.stored_index = None
        self.stored_meta = None

    async def set_token_index(self, index):
        self.stored_index = index

    async def set_token_index_meta(self, meta):
        self.stored_meta = meta


async def test_sync_once_builds_index_and_filters_single_chain_tokens():
    chains = [
        {"id": 1, "name": "Ethereum"},
        {"id": 42161, "name": "Arbitrum One"},
    ]
    tokens_by_chain = {
        "1": [{"symbol": "USDT", "priceUSD": "1"}, {"symbol": "onlyoneth", "priceUSD": "1"}],
        "42161": [{"symbol": "usdt", "priceUSD": "1"}],
    }
    client = FakeLiFiClient(chains, tokens_by_chain)
    cache = RecordingCache()
    service = TokenIndexSyncService(client=client, cache=cache, interval_hours=8)

    await service.sync_once()

    assert cache.stored_index == {"USDT": ["Arbitrum", "Ethereum"]}


async def test_sync_once_indexes_any_chain_lifi_reports_not_just_a_fixed_list():
    chains = [
        {"id": 1, "name": "Ethereum"},
        {"id": 999999, "name": "Some Brand New L2"},
    ]
    tokens_by_chain = {
        "1": [{"symbol": "OBSCURE", "priceUSD": "0.5"}],
        "999999": [{"symbol": "obscure", "priceUSD": "0.5"}],
    }
    client = FakeLiFiClient(chains, tokens_by_chain)
    cache = RecordingCache()
    service = TokenIndexSyncService(client=client, cache=cache, interval_hours=8)

    await service.sync_once()

    assert cache.stored_index == {"OBSCURE": ["Ethereum", "Some Brand New L2"]}


async def test_sync_once_renames_known_chain_aliases_and_skips_testnets():
    chains = [
        {"id": 56, "name": "BSC"},
        {"id": 137, "name": "Polygon PoS"},
        {"id": 5, "name": "Goerli", "mainnet": False},
    ]
    tokens_by_chain = {
        "56": [{"symbol": "TOK", "priceUSD": "2"}],
        "137": [{"symbol": "TOK", "priceUSD": "2"}],
        "5": [{"symbol": "TOK", "priceUSD": "2"}],
    }
    client = FakeLiFiClient(chains, tokens_by_chain)
    cache = RecordingCache()
    service = TokenIndexSyncService(client=client, cache=cache, interval_hours=8)

    await service.sync_once()

    assert cache.stored_index == {"TOK": ["BNB Chain", "Polygon"]}


async def test_sync_once_skips_tokens_without_price_data():
    # Li.Fi lists per-chain tokens for basically any deployed contract, so
    # spam/scam tokens with no real price data must not be indexed — that's
    # what previously let e.g. an unrelated "XLM"-symbol contract on some
    # random EVM chain get conflated with the real Stellar Lumens.
    chains = [
        {"id": 1, "name": "Ethereum"},
        {"id": 56, "name": "BSC"},
    ]
    tokens_by_chain = {
        "1": [{"symbol": "SPAM", "priceUSD": "1"}],
        "56": [{"symbol": "SPAM"}],  # no priceUSD -> unpriced/unverified
    }
    client = FakeLiFiClient(chains, tokens_by_chain)
    cache = RecordingCache()
    service = TokenIndexSyncService(client=client, cache=cache, interval_hours=8)

    await service.sync_once()

    # Only found on Ethereum with price data -> below the 2-chain threshold.
    assert cache.stored_index is None


async def test_sync_once_groups_by_coin_key_instead_of_raw_symbol_when_available():
    # Two unrelated contracts on different chains sharing the "DUP" symbol
    # must not be merged just because the text matches; Li.Fi's coinKey
    # (its own cross-chain identifier for a *recognized* asset) disambiguates.
    chains = [
        {"id": 1, "name": "Ethereum"},
        {"id": 56, "name": "BSC"},
        {"id": 137, "name": "Polygon PoS"},
    ]
    tokens_by_chain = {
        "1": [{"symbol": "DUP", "coinKey": "REALPROJECT", "priceUSD": "3"}],
        "56": [{"symbol": "DUP", "coinKey": "REALPROJECT", "priceUSD": "3"}],
        "137": [{"symbol": "DUP", "priceUSD": "0.0001"}],  # unrelated scam reusing the symbol
    }
    client = FakeLiFiClient(chains, tokens_by_chain)
    cache = RecordingCache()
    service = TokenIndexSyncService(client=client, cache=cache, interval_hours=8)

    await service.sync_once()

    assert cache.stored_index == {"REALPROJECT": ["BNB Chain", "Ethereum"]}


async def test_sync_once_records_diagnostic_metadata():
    chains = [
        {"id": 1, "name": "Ethereum"},
        {"id": 42161, "name": "Arbitrum One"},
        {"id": 10, "name": "Optimism"},
    ]
    tokens_by_chain = {
        "1": [{"symbol": "USDT", "priceUSD": "1"}],
        "42161": [{"symbol": "USDT", "priceUSD": "1"}],
        "10": [],  # Li.Fi returned nothing for this chain
    }
    client = FakeLiFiClient(chains, tokens_by_chain)
    cache = RecordingCache()
    service = TokenIndexSyncService(client=client, cache=cache, interval_hours=8)

    await service.sync_once()

    assert cache.stored_meta["chain_count"] == 3
    assert cache.stored_meta["chains_with_tokens"] == 2
    assert cache.stored_meta["ticker_count"] == 1
    assert "updated_at" in cache.stored_meta


async def test_sync_once_survives_client_failure():
    class FailingClient:
        async def fetch_chains(self):
            raise RuntimeError("network down")

        async def fetch_tokens_by_chain(self, chain_ids):
            return {}

    cache = RecordingCache()
    service = TokenIndexSyncService(client=FailingClient(), cache=cache, interval_hours=8)

    await service.sync_once()

    assert cache.stored_index is None


async def test_sync_once_notifies_after_repeated_failures():
    class FailingClient:
        async def fetch_chains(self):
            raise RuntimeError("Li.Fi is down")

        async def fetch_tokens_by_chain(self, chain_ids):
            return {}

    messages: list[str] = []

    async def notify(text: str) -> None:
        messages.append(text)

    cache = RecordingCache()
    service = TokenIndexSyncService(client=FailingClient(), cache=cache, interval_hours=8, notify=notify)

    await service.sync_once()
    await service.sync_once()
    assert messages == []

    await service.sync_once()
    assert len(messages) == 1
    assert "Li.Fi sync" in messages[0]
