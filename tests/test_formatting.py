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


def test_format_bridges_message_flags_auto_detected():
    bridges = [
        BridgeInfo(
            key="lifi",
            display_name="LI.FI (Jumper)",
            url="https://jumper.exchange",
            networks=["Ethereum", "Arbitrum"],
            auto_detected=True,
        )
    ]

    text = format_bridges_message("LSK", bridges)

    assert "маршрут" in text.lower()
    assert "Доступные мосты" in text


def test_format_bridges_message_mentions_layerzero_note_for_auto_detected():
    bridges = [
        BridgeInfo(
            key="lifi",
            display_name="LI.FI (Jumper)",
            url="https://jumper.exchange",
            networks=["Ethereum", "Arbitrum"],
            auto_detected=True,
        )
    ]

    text = format_bridges_message("WLFI", bridges)

    assert "LayerZero" in text
    assert "layerzeroscan.com" in text


def test_format_bridges_message_no_layerzero_note_for_curated_results():
    bridges = [
        BridgeInfo(
            key="stargate",
            display_name="Stargate Finance",
            url="https://stargate.finance",
            networks=["Ethereum", "Arbitrum"],
        )
    ]

    text = format_bridges_message("USDT", bridges)

    assert "LayerZero" not in text


def test_format_bridges_message_no_disclaimer_for_curated_results():
    bridges = [
        BridgeInfo(
            key="stargate",
            display_name="Stargate Finance",
            url="https://stargate.finance",
            networks=["Ethereum", "Arbitrum"],
        )
    ]

    text = format_bridges_message("USDT", bridges)

    assert "проверяйте маршрут" not in text.lower()
    assert "Доступные мосты" in text


def test_format_not_found_with_suggestions():
    text = format_not_found_message("USDR", ["USDT", "USDC"])

    assert "USDR" in text
    assert "USDT" in text
    assert "USDC" in text


def test_format_not_found_without_suggestions():
    text = format_not_found_message("ZZZZ", [])

    assert "ZZZZ" in text
    assert "Возможно" not in text


def test_format_not_found_includes_miss_reason_when_provided():
    text = format_not_found_message("ZZZZ", [], miss_reason="в живом индексе Li.Fi отсутствует")

    assert "в живом индексе Li.Fi отсутствует" in text


def test_format_not_found_omits_miss_reason_when_absent():
    text = format_not_found_message("ZZZZ", [])

    assert "🔍" not in text
