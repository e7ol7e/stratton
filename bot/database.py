import unicodedata
from pathlib import Path

import aiosqlite


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


class Database:
    def __init__(self, path: str):
        self.path = path

    async def initialize(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS words (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    word TEXT NOT NULL,
                    word_key TEXT NOT NULL,
                    translation TEXT NOT NULL,
                    UNIQUE(user_id, word_key)
                );
                CREATE TABLE IF NOT EXISTS results (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    correct INTEGER NOT NULL,
                    total INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CHECK(total > 0 AND correct >= 0 AND correct <= total)
                );
                CREATE INDEX IF NOT EXISTS results_user ON results(user_id);
            """)
            await db.commit()

    async def add_word(self, user_id: int, word: str, translation: str) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "INSERT INTO words(user_id, word, word_key, translation) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id, word_key) DO NOTHING",
                (user_id, word, normalize(word), translation),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def words(self, user_id: int, limit: int = 10, random: bool = False) -> list[dict]:
        order = "RANDOM()" if random else "id DESC"
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT word, translation FROM words WHERE user_id = ? ORDER BY {order} LIMIT ?",
                (user_id, limit),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def save_result(self, session_id: str, user_id: int, correct: int, total: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO results(session_id, user_id, correct, total) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(session_id) DO NOTHING",
                (session_id, user_id, correct, total),
            )
            await db.commit()

    async def stats(self, user_id: int) -> dict:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT COUNT(*) AS tests, COALESCE(SUM(correct), 0) AS correct,
                       COALESCE(SUM(total), 0) AS total,
                       (SELECT COUNT(*) FROM words WHERE user_id = ?) AS words
                FROM results WHERE user_id = ?
            """, (user_id, user_id))
            return dict(await cursor.fetchone())
