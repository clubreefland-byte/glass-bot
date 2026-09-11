import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncpg

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Получение переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = os.getenv("ADMIN_ID")

if ADMIN_ID:
    try:
        ADMIN_ID = int(ADMIN_ID)
    except ValueError:
        ADMIN_ID = None

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db_pool = None


# Определение состояний FSM
class CalcState(StatesGroup):
    waiting_for_dimensions = State()


# Инициализация базы данных Supabase (PostgreSQL)
async def init_db_pool():
    global db_pool
    if not DATABASE_URL:
        logging.error("ОШИБКА: Переменная окружения DATABASE_URL не задана!")
        return

    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    try:
        # Для Supabase требуется SSL-соединение
        db_pool = await asyncpg.create_pool(
            dsn=url, min_size=1, max_size=10, ssl="require"
        )

        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    name TEXT,
                    username TEXT,
                    calculations INTEGER DEFAULT 0
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS calculations (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    volume_l INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        logging.info(
            "База данных PostgreSQL (Supabase) успешно инициализирована!"
        )
    except Exception as e:
        logging.error(f"Ошибка подключения к БД: {e}")


# Вспомогательные функции взаимодействия с БД
async def register_or_update_user(user: types.User):
    if not db_pool:
        return
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (user_id, name, username, calculations)
            VALUES ($1, $2, $3, 0)
            ON CONFLICT (user_id) DO UPDATE 
            SET name = EXCLUDED.name, username = EXCLUDED.username;
        """,
            user.id,
            user.full_name,
            user.username,
        )


async def record_calculation(user_id: int, volume_l: int):
    if not db_pool:
        return
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO calculations (user_id, volume_l) VALUES ($1, $2);",
            user_id,
            volume_l,
        )
        await conn.execute(
            "UPDATE users SET calculations = calculations + 1 WHERE user_id = $1;",
            user_id,
        )


# Обработчики команд
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await register_or_update_user(message.from_user)
    await state.set_state(CalcState.waiting_for_dimensions)
    await message.answer(
        "Привет! Я бот для расчёта параметров аквариума.\n\n"
        "Введите размеры аквариума в сантиметрах в формате: **Длина Ширина Высота**\n"
        "(например: `100 50 50`)"
    )


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if ADMIN_ID and message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет прав для просмотра статистики.")
        return

    if not db_pool:
        await message.answer("База данных временно недоступна.")
        return

    async with db_pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users;")
        total_calcs = await conn.fetchval("SELECT COUNT(*) FROM calculations;")

    await message.answer(
        f"📊 **Статистика бота (Supabase PG):**\n\n"
        f"👤 Всего пользователей: `{total_users}`\n"
        f"🧮 Выполнено расчётов: `{total_calcs}`"
    )


# Обработка ввода размеров
@dp.message(CalcState.waiting_for_dimensions)
async def process_dimensions(message: types.Message, state: FSMContext):
    text = message.text.strip()
    parts = text.split()

    if len(parts) != 3:
        await message.answer(
            "Пожалуйста, введите 3 числа через пробел (Длина Ширина Высота), например: `100 50 50`"
        )
        return

    try:
        length = float(parts[0].replace(",", "."))
        width = float(parts[1].replace(",", "."))
        height = float(parts[2].replace(",", "."))
    except ValueError:
        await message.answer(
            "Ошибка ввода. Используйте только числа, разделенные пробелом."
        )
        return

    # Расчёт объёма в литрах
    volume_l = int((length * width * height) / 1000)

    # Запись в БД
    await record_calculation(message.from_user.id, volume_l)

    response = (
        f"📐 **Результаты расчёта:**\n\n"
        f"Габариты: {length} × {width} × {height} см\n"
        f"Объём аквариума: **{volume_l} л**\n\n"
        f"Введите новые размеры для следующего расчёта."
    )

    await message.answer(response, parse_mode="Markdown")


async def main():
    await init_db_pool()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
