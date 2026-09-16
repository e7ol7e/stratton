import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.types import BotCommand
from dotenv import load_dotenv

from bot.database import Database
from bot.handlers import router


async def main():
    load_dotenv()
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), RotatingFileHandler(
            "logs/bot.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8",
        )],
    )
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Укажите BOT_TOKEN в .env (см. .env.example).")
    db = Database(os.getenv("DATABASE_PATH", "data/vocabulary.sqlite3"))
    await db.initialize()
    dp = Dispatcher(storage=MemoryStorage(), events_isolation=SimpleEventIsolation())
    dp.include_router(router)
    async with Bot(token=token) as bot:
        await bot.set_my_commands([BotCommand(command=command, description=description) for command, description in [
            ("start", "Главное меню"), ("add", "Добавить слово"), ("test", "Начать тест"),
            ("stats", "Результаты"), ("words", "Мои слова"), ("cancel", "Отмена"),
        ]])
        logging.info("Bot starting")
        try:
            await dp.start_polling(bot, db=db, allowed_updates=["message"], close_bot_session=False)
        finally:
            await dp.storage.close()
            logging.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        logging.exception("Bot terminated unexpectedly")
        raise SystemExit(1)
