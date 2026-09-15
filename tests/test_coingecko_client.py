from app.services.coingecko_client import CoinGeckoClient


def test_no_api_key_omits_demo_header():
    client = CoinGeckoClient("https://api.coingecko.com/api/v3", 3.0)

    assert "x-cg-demo-api-key" not in client._headers
    assert "User-Agent" in client._headers


def test_api_key_is_sent_as_demo_header():
    client = CoinGeckoClient("https://api.coingecko.com/api/v3", 3.0, api_key="demo-key-123")

    assert client._headers["x-cg-demo-api-key"] == "demo-key-123"
