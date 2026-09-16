import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.database import Database, normalize
from bot.handlers import Quiz, receive_answer, receive_word, AddWord


class BotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.temp.name) / "test.sqlite3"))
        await self.db.initialize()
        self.storage = MemoryStorage()
        self.state = FSMContext(self.storage, StorageKey(bot_id=1, chat_id=1, user_id=1))

    async def asyncTearDown(self):
        await self.storage.close()
        self.temp.cleanup()

    async def test_duplicates_isolation_and_persistence(self):
        self.assertTrue(await self.db.add_word(1, "Hello", "привет"))
        self.assertFalse(await self.db.add_word(1, " HELLO ", "здравствуйте"))
        self.assertTrue(await self.db.add_word(2, "hello", "другой перевод"))
        reopened = Database(self.db.path)
        await reopened.initialize()
        self.assertEqual(await reopened.words(1), [{"word": "Hello", "translation": "привет"}])
        self.assertEqual(await reopened.words(3), [])

    async def test_results_are_idempotent_and_private(self):
        await self.db.save_result("a", 1, 2, 3)
        await self.db.save_result("a", 1, 2, 3)
        await self.db.save_result("b", 1, 1, 2)
        await self.db.save_result("c", 2, 5, 5)
        self.assertEqual(await self.db.stats(1), {"tests": 2, "correct": 3, "total": 5, "words": 0})
        self.assertEqual((await self.db.stats(3))["total"], 0)

    async def test_quiz_completes_and_scores(self):
        await self.state.set_state(Quiz.answer)
        await self.state.set_data({"words": [
            {"word": "cat", "translation": "кот"},
            {"word": "dog", "translation": "собака"},
        ], "index": 0, "correct": 0, "session_id": "quiz"})
        message = AsyncMock()
        message.from_user.id = 1
        message.text = " КОТ "
        await receive_answer(message, self.state, self.db)
        self.assertEqual((await self.state.get_data())["index"], 1)
        self.assertEqual((await self.db.stats(1))["tests"], 0)
        message.text = "неверно"
        await receive_answer(message, self.state, self.db)
        self.assertIsNone(await self.state.get_state())
        self.assertEqual((await self.db.stats(1))["correct"], 1)
        self.assertEqual((await self.db.stats(1))["total"], 2)

    async def test_invalid_input_keeps_state(self):
        await self.state.set_state(AddWord.word)
        message = AsyncMock()
        message.text = None
        await receive_word(message, self.state)
        self.assertEqual(await self.state.get_state(), AddWord.word.state)
        message.text = "  hello  "
        await receive_word(message, self.state)
        self.assertEqual(await self.state.get_state(), AddWord.translation.state)
        self.assertEqual((await self.state.get_data())["word"], "hello")

    def test_normalization(self):
        self.assertEqual(normalize("  ＨＥＬＬＯ   World "), "hello world")
