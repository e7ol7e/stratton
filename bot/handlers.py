import logging
from uuid import uuid4

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ErrorEvent, KeyboardButton, Message, ReplyKeyboardMarkup

from bot.database import Database, normalize

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(F.chat.type == "private")

MENU = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="➕ Добавить слово"), KeyboardButton(text="📝 Тест")],
    [KeyboardButton(text="📊 Результаты"), KeyboardButton(text="📚 Мои слова")],
    [KeyboardButton(text="Отмена")],
], resize_keyboard=True)


class AddWord(StatesGroup):
    word = State()
    translation = State()


class Quiz(StatesGroup):
    answer = State()


@router.message(CommandStart())
@router.message(Command("help"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Я помогу учить слова.\n\n"
        "/add — добавить слово и перевод\n/test — тест до 10 слов\n"
        "/stats — результаты\n/words — последние 10 слов\n"
        "/cancel — отмена\n\nВ тесте напишите перевод показанного слова. "
        "Регистр и лишние пробелы не учитываются. "
        "В статистику входят только завершённые тесты.", reply_markup=MENU,
    )


@router.message(Command("cancel"))
@router.message(F.text == "Отмена")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено. Выберите пункт меню.", reply_markup=MENU)


@router.message(StateFilter(None), Command("add"))
@router.message(StateFilter(None), F.text == "➕ Добавить слово")
async def add(message: Message, state: FSMContext):
    await state.set_state(AddWord.word)
    await message.answer("Введите слово или фразу (до 100 символов). Для отмены: /cancel.")


@router.message(StateFilter(None), Command("test"))
@router.message(StateFilter(None), F.text == "📝 Тест")
async def test(message: Message, state: FSMContext, db: Database):
    words = await db.words(message.from_user.id, random=True)
    if not words:
        await message.answer("Словарь пуст. Сначала добавьте слово: /add.")
        return
    await state.set_data({"words": words, "index": 0, "correct": 0, "session_id": uuid4().hex})
    await state.set_state(Quiz.answer)
    await ask_question(message, words, 0)


@router.message(Command("stats"))
@router.message(F.text == "📊 Результаты")
async def stats(message: Message, db: Database):
    result = await db.stats(message.from_user.id)
    percent = 100 * result["correct"] / result["total"] if result["total"] else 0
    await message.answer(
        f"📊 Слов: {result['words']}\nЗавершено тестов: {result['tests']}\n"
        f"Верных ответов: {result['correct']} из {result['total']}\nТочность: {percent:.1f}%"
    )


@router.message(Command("words"))
@router.message(F.text == "📚 Мои слова")
async def words(message: Message, db: Database):
    entries = await db.words(message.from_user.id)
    await message.answer("📚 Последние 10 слов:\n" + "\n".join(
        f"• {item['word']} — {item['translation']}" for item in entries
    ) if entries else "Словарь пуст. Добавьте слово: /add.")


# Commands and menu buttons must never become vocabulary entries or quiz answers.
@router.message(F.text.startswith("/"))
@router.message(F.text.in_({"➕ Добавить слово", "📝 Тест"}))
async def unknown_command(message: Message, state: FSMContext):
    if await state.get_state():
        await message.answer("Сначала завершите текущее действие или нажмите /cancel.")
    else:
        await message.answer("Неизвестная команда. Список команд: /help.")


def valid_text(message: Message) -> bool:
    return bool(message.text and normalize(message.text) and len(message.text) <= 100)


@router.message(AddWord.word)
async def receive_word(message: Message, state: FSMContext):
    if not valid_text(message):
        await message.answer("Нужно текстовое слово или фраза от 1 до 100 символов.")
        return
    await state.update_data(word=" ".join(message.text.split()))
    await state.set_state(AddWord.translation)
    await message.answer("Теперь введите один перевод (до 100 символов).")


@router.message(AddWord.translation)
async def receive_translation(message: Message, state: FSMContext, db: Database):
    if not valid_text(message):
        await message.answer("Введите перевод текстом: от 1 до 100 символов.")
        return
    data = await state.get_data()
    added = await db.add_word(message.from_user.id, data["word"], " ".join(message.text.split()))
    await state.clear()
    logger.info("Word addition user_id=%s added=%s", message.from_user.id, added)
    await message.answer("✅ Слово добавлено!" if added else "Это слово уже есть в вашем словаре.", reply_markup=MENU)


async def ask_question(message: Message, words: list[dict], index: int):
    await message.answer(f"Вопрос {index + 1}/{len(words)}. Напишите перевод:\n{words[index]['word']}")


@router.message(Quiz.answer)
async def receive_answer(message: Message, state: FSMContext, db: Database):
    if not valid_text(message):
        await message.answer("Введите ответ текстом: от 1 до 100 символов.")
        return
    data = await state.get_data()
    index, entries = data["index"], data["words"]
    expected = entries[index]["translation"]
    right = normalize(message.text) == normalize(expected)
    correct = data["correct"] + int(right)
    feedback = "✅ Верно!" if right else f"❌ Правильный перевод: {expected}"
    index += 1
    if index == len(entries):
        await db.save_result(data["session_id"], message.from_user.id, correct, len(entries))
        await state.clear()
        logger.info("Quiz completed user_id=%s correct=%s total=%s", message.from_user.id, correct, len(entries))
        await message.answer(
            f"{feedback}\n\nТест завершён! Результат: {correct}/{len(entries)} "
            f"({100 * correct / len(entries):.0f}%).\nЕщё один тест: /test", reply_markup=MENU,
        )
    else:
        await state.update_data(index=index, correct=correct)
        await message.answer(feedback)
        await ask_question(message, entries, index)


@router.message()
async def fallback(message: Message):
    await message.answer("Выберите действие в меню или отправьте /help.", reply_markup=MENU)


@router.error()
async def handle_error(event: ErrorEvent, state: FSMContext | None = None):
    logger.error("Update failed update_id=%s", event.update.update_id,
                 exc_info=(type(event.exception), event.exception, event.exception.__traceback__))
    if state is not None:
        await state.clear()
    if event.update.message:
        try:
            await event.update.message.answer("Произошла ошибка. Попробуйте снова через меню: /start.")
        except TelegramAPIError:
            logger.warning("Could not send error notification")
    return True
