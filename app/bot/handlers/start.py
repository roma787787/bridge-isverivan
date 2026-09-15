from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="start")

WELCOME_TEXT = (
    "\U0001f44b Привет! Я <b>BridgeFinder</b> — бот для поиска кроссчейн-мостов.\n\n"
    "Отправь мне тикер криптовалюты (например, <code>USDT</code>, <code>ETH</code>, <code>SOL</code>, "
    "<code>WBTC</code>), и я покажу, какие мосты его поддерживают, в каких сетях, и дам прямые ссылки "
    "на сервисы.\n\n"
    "Регистр не важен: <code>usdt</code>, <code>Usdt</code> и <code>USDT</code> — это одно и то же."
)


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(WELCOME_TEXT)
