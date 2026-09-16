from __future__ import annotations

from html import escape

from ..services.bridge_repository import BridgeInfo


def format_bridges_message(ticker: str, bridges: list[BridgeInfo]) -> str:
    is_auto_detected = any(bridge.auto_detected for bridge in bridges)
    lines = [f"\U0001f309 <b>Доступные мосты для {escape(ticker)}:</b>", ""]
    for index, bridge in enumerate(bridges, start=1):
        networks = ", ".join(escape(network) for network in bridge.networks)
        lines.append(f"{index}. <b>{escape(bridge.display_name)}</b>")
        lines.append(f"• Поддерживаемые сети: {networks}")
        lines.append(f"• Ссылка: {escape(bridge.url)}")
        lines.append("")

    if is_auto_detected:
        lines.append(
            "⚠️ Наличие конкретного пула ликвидности не гарантировано — проверяйте маршрут и сумму "
            "на сайте перед переводом."
        )
        lines.append(
            "ℹ️ Если у этого токена есть собственный нативный мост на LayerZero (OFT-стандарт), "
            "ищите его на официальном сайте проекта — такие мосты у каждого проекта свои, единого "
            "интерфейса нет. Проверить сам факт LayerZero-перевода можно на https://layerzeroscan.com"
        )

    return "\n".join(lines).rstrip()


def format_not_found_message(ticker: str, suggestions: list[str], miss_reason: str | None = None) -> str:
    text = f"\U0001f615 Пока не нашёл мостов, поддерживающих <b>{escape(ticker)}</b>."
    if suggestions:
        options = ", ".join(f"<code>{escape(s)}</code>" for s in suggestions)
        text += f"\n\nВозможно, вы имели в виду: {options}?"
    else:
        text += "\n\nПроверьте правильность тикера или попробуйте другой (например, USDT, ETH, SOL)."
    if miss_reason:
        text += f"\n\n\U0001f50d <i>{escape(miss_reason)}</i>"
    return text


def format_invalid_input_message() -> str:
    return (
        "\U0001f914 Не удалось распознать тикер. "
        "Отправьте, например, <code>USDT</code>, <code>ETH</code> или <code>SOL</code>."
    )
