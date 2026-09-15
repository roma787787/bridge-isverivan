from app.bot.handlers.search import _TICKER_RE


def test_ticker_regex_accepts_single_character_tickers():
    assert _TICKER_RE.match("W")
    assert _TICKER_RE.match("$W")


def test_ticker_regex_accepts_typical_tickers():
    for ticker in ["USDT", "usdt", "$eth", "WBTC", "a1b2"]:
        assert _TICKER_RE.match(ticker), ticker


def test_ticker_regex_rejects_empty_and_invalid_input():
    for invalid in ["", "   ", "hello world", "usdt!", "-", "$"]:
        assert not _TICKER_RE.match(invalid), invalid


def test_ticker_regex_rejects_too_long_input():
    assert not _TICKER_RE.match("A" * 16)
    assert _TICKER_RE.match("A" * 15)
