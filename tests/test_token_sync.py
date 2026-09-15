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

    async def set_token_index(self, index):
        self.stored_index = index


async def test_sync_once_builds_index_and_filters_single_chain_tokens():
    chains = [
        {"id": 1, "name": "Ethereum"},
        {"id": 42161, "name": "Arbitrum One"},
        {"id": 999999, "name": "SomeUnknownChain"},
    ]
    tokens_by_chain = {
        "1": [{"symbol": "USDT"}, {"symbol": "onlyoneth"}],
        "42161": [{"symbol": "usdt"}],
    }
    client = FakeLiFiClient(chains, tokens_by_chain)
    cache = RecordingCache()
    service = TokenIndexSyncService(client=client, cache=cache, interval_hours=8)

    await service.sync_once()

    assert cache.stored_index == {"USDT": ["Arbitrum", "Ethereum"]}


async def test_sync_once_ignores_unrecognized_chains():
    chains = [{"id": 1, "name": "SomeChainWeDontTrack"}]
    client = FakeLiFiClient(chains, {})
    cache = RecordingCache()
    service = TokenIndexSyncService(client=client, cache=cache, interval_hours=8)

    await service.sync_once()

    assert cache.stored_index is None


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
