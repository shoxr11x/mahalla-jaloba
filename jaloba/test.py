import os
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import asyncio
from dotenv import load_dotenv

async def main():
    load_dotenv()
    bot = Bot(
        os.getenv("BOT_TOKEN"),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    chat_id = os.getenv("ZAYAVKI_CHAT_ID")
    await bot.send_message(chat_id, "✅ Тестовое сообщение в группу")

asyncio.run(main())
