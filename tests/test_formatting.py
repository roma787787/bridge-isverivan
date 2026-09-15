from app.bot.formatting import format_bridges_message, format_not_found_message
from app.services.bridge_repository import BridgeInfo


def test_format_bridges_message_contains_expected_fields():
    bridges = [
        BridgeInfo(
            key="stargate",
            display_name="Stargate Finance",
            url="https://stargate.finance",
            networks=["Ethereum", "Arbitrum"],
        )
    ]

    text = format_bridges_message("USDT", bridges)

    assert "USDT" in text
    assert "Stargate Finance" in text
    assert "https://stargate.finance" in text
    assert "Ethereum, Arbitrum" in text


def test_format_bridges_message_escapes_html():
    bridges = [
        BridgeInfo(key="x", display_name="<script>", url="https://example.com", networks=["A & B"]),
    ]

    text = format_bridges_message("USDT", bridges)

    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "A &amp; B" in text


def test_format_not_found_with_suggestions():
    text = format_not_found_message("USDR", ["USDT", "USDC"])

    assert "USDR" in text
    assert "USDT" in text
    assert "USDC" in text


def test_format_not_found_without_suggestions():
    text = format_not_found_message("ZZZZ", [])

    assert "ZZZZ" in text
    assert "Возможно" not in text
