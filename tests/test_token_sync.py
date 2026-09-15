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


async def test_sync_once_indexes_any_chain_lifi_reports_not_just_a_fixed_list():
    chains = [
        {"id": 1, "name": "Ethereum"},
        {"id": 999999, "name": "Some Brand New L2"},
    ]
    tokens_by_chain = {
        "1": [{"symbol": "OBSCURE"}],
        "999999": [{"symbol": "obscure"}],
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
        "56": [{"symbol": "TOK"}],
        "137": [{"symbol": "TOK"}],
        "5": [{"symbol": "TOK"}],
    }
    client = FakeLiFiClient(chains, tokens_by_chain)
    cache = RecordingCache()
    service = TokenIndexSyncService(client=client, cache=cache, interval_hours=8)

    await service.sync_once()

    assert cache.stored_index == {"TOK": ["BNB Chain", "Polygon"]}


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
