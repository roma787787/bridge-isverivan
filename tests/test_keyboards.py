from app.bot.keyboards import build_bridges_keyboard
from app.services.bridge_repository import BridgeInfo


def test_build_bridges_keyboard_one_button_per_bridge():
    bridges = [
        BridgeInfo(key="a", display_name="Bridge A", url="https://a.example", networks=["Ethereum"]),
        BridgeInfo(key="b", display_name="Bridge B", url="https://b.example", networks=["Base"]),
    ]

    keyboard = build_bridges_keyboard(bridges)

    assert len(keyboard.inline_keyboard) == 2
    assert keyboard.inline_keyboard[0][0].text.startswith("Bridge A")
    assert keyboard.inline_keyboard[0][0].url == "https://a.example"
    assert keyboard.inline_keyboard[1][0].text.startswith("Bridge B")
    assert keyboard.inline_keyboard[1][0].url == "https://b.example"


def test_build_bridges_keyboard_empty_list():
    keyboard = build_bridges_keyboard([])

    assert keyboard.inline_keyboard == []
