import asyncio
import os
import logging
from urllib.parse import quote
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import asyncpg

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
DATABASE_URL = os.getenv("DATABASE_URL")

ADMIN_ID = 1318763491

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None

PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher(storage=MemoryStorage())

CHANNEL_USERNAME = "@club_reefland"

db_pool = None

async def init_db_pool():
    global db_pool
    if not DATABASE_URL:
        logging.error("ОШИБКА: DATABASE_URL не задан!")
        return

    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    db_pool = await asyncpg.create_pool(dsn=url, min_size=1, max_size=10)

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
    logging.info("База данных PostgreSQL успешно инициализирована!")


async def db_register_user(user: types.User):
    if not db_pool:
        return
    full_name = user.full_name or "Без имени"
    username = f"@{user.username}" if user.username else "нет username"

    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, name, username, calculations)
            VALUES ($1, $2, $3, 0)
            ON CONFLICT (user_id) DO UPDATE SET
                name = EXCLUDED.name,
                username = EXCLUDED.username;
        """, user.id, full_name, username)


async def db_increment_calc(user: types.User, volume_l: int):
    if not db_pool:
        return
    await db_register_user(user)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET calculations = calculations + 1 WHERE user_id = $1;", user.id)
        await conn.execute("INSERT INTO calculations (user_id, volume_l) VALUES ($1, $2);", user.id, volume_l)


async def db_get_stats():
    if not db_pool:
        return 0, 0, {}, []

    async with db_pool.acquire() as conn:
        res = await conn.fetchrow("SELECT COUNT(*), SUM(calculations) FROM users;")
        total_users = res[0] or 0
        total_calcs = res[1] or 0

        rows = await conn.fetch("SELECT volume_l FROM calculations WHERE volume_l IS NOT NULL;")
        volumes = [r['volume_l'] for r in rows]

        calc_count = len(volumes) if len(volumes) > 0 else total_calcs

        v_under_50 = sum(1 for v in volumes if v < 50)
        v_50_150 = sum(1 for v in volumes if 50 <= v < 150)
        v_150_300 = sum(1 for v in volumes if 150 <= v < 300)
        v_over_300 = sum(1 for v in volumes if v >= 300)

        top_users = await conn.fetch(
            "SELECT name, username, calculations FROM users ORDER BY calculations DESC LIMIT 20;"
        )

    volume_stats = {
        "under_50": (v_under_50, round((v_under_50 / calc_count * 100), 1) if calc_count else 0),
        "50_150": (v_50_150, round((v_50_150 / calc_count * 100), 1) if calc_count else 0),
        "150_300": (v_150_300, round((v_150_300 / calc_count * 100), 1) if calc_count else 0),
        "over_300": (v_over_300, round((v_over_300 / calc_count * 100), 1) if calc_count else 0)
    }

    return total_users, total_calcs, volume_stats, top_users


async def check_user_subscription(user_id: int) -> bool:
    if not bot:
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        if member.status in ["creator", "administrator", "member"]:
            return True
        return False
    except TelegramBadRequest:
        return True
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        return True


def get_subscribe_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на Reefland", url="https://t.me/club_reefland")],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_sub")]
        ]
    )


def get_start_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Канал Reefland", url="https://t.me/club_reefland")]
        ]
    )


def get_result_keyboard(length, width, height, rec):
    l_int, w_int, h_int, r_int = int(round(length)), int(round(width)), int(round(height)), int(round(rec))
    calc_text = f"Здравствуйте! Интересует стоимость изготовления аквариума {l_int}х{w_int}х{h_int}см из стекла {r_int}мм."
    lead_url = f"https://t.me/Asteriy78?text={quote(calc_text)}"

    share_text = quote(
        f"📐 Я рассчитал толщину стекла для аквариума {l_int}×{w_int}×{h_int} см!\n"
        f"Рекомендуемая толщина: {r_int} мм (Optiwhite / М1)."
    )
    share_url = f"https://t.me/share/url?url=https://t.me/AquaGlassCalcBot&text={share_text}"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📩 Узнать стоимость изготовления", url=lead_url)],
            [InlineKeyboardButton(text="📤 Поделиться результатом", url=share_url)],
            [InlineKeyboardButton(text="📢 Канал Reefland", url="https://t.me/club_reefland")]
        ]
    )


def calculate_glass_thickness(length_cm: float, width_cm: float, height_cm: float) -> tuple[float, int, str]:
    if height_cm <= 0 or length_cm <= 0 or width_cm <= 0:
        raise ValueError("Размеры должны быть больше нуля.")

    l, w, h = int(round(length_cm)), int(round(width_cm)), int(round(height_cm))

    EXACT_STANDARDS = {
        (30, 30, 30): 6, (40, 40, 40): 6, (45, 45, 45): 8, (50, 50, 50): 8,   
        (60, 60, 60): 10, (70, 70, 70): 12, (80, 80, 80): 15,
        (45, 30, 30): 6, (60, 30, 36): 6, (60, 30, 40): 6, 
        (60, 40, 40): 8, (60, 45, 45): 8, (80, 35, 40): 8, 
        (80, 45, 45): 10, (90, 45, 45): 10, (90, 50, 50): 10, (100, 40, 40): 10, (100, 45, 45): 10, 
        (70, 60, 60): 12, (90, 60, 60): 12, (100, 50, 50): 12, (120, 50, 50): 12, (120, 50, 60): 12,
        (120, 60, 60): 15, (150, 60, 50): 15, (160, 50, 50): 15,
        (150, 50, 50): 15, (150, 50, 60): 15, (150, 60, 60): 15, (160, 60, 60): 15,
        (170, 60, 50): 15, (170, 60, 60): 15, (180, 60, 50): 15,
        (180, 60, 60): 15, (180, 70, 70): 15, (200, 60, 60): 15, (200, 70, 70): 15
    }

    if (l, w, h) in EXACT_STANDARDS:
        rec_mm = EXACT_STANDARDS[(l, w, h)]
    elif (w, l, h) in EXACT_STANDARDS:
        rec_mm = EXACT_STANDARDS[(w, l, h)]
    else:
        max_side = max(length_cm, width_cm)
        if height_cm <= 35:
            rec_mm = 6 if max_side <= 60 else (8 if max_side <= 100 else 10)
        elif height_cm <= 45:
            rec_mm = 6 if max_side <= 60 else (8 if max_side <= 90 else (10 if max_side <= 120 else 12))
        elif height_cm <= 52:
            rec_mm = 8 if max_side <= 55 else (10 if max_side <= 100 else (12 if max_side <= 140 else 15))
        elif height_cm <= 62:
            rec_mm = 10 if max_side <= 65 else (12 if max_side <= 130 else 15)
        elif height_cm <= 72:
            rec_mm = 15
        else:
            rec_mm = 19

    max_side = max(length_cm, width_cm)
    bracing_text = "Не требуются"
    if rec_mm == 15 and height_cm <= 52 and max_side <= 160:
        bracing_text = "Не требуются"
    elif max_side > 160 or (rec_mm == 15 and max_side >= 150 and height_cm >= 60) or height_cm >= 70:
        bracing_text = "Требуются рёбра жесткости и стяжки"
    elif max_side >= 130 or (height_cm >= 65 and rec_mm < 15):
        bracing_text = "Рекомендуются рёбра жесткости"

    return float(rec_mm), rec_mm, bracing_text


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await db_register_user(message.from_user)

    if not await check_user_subscription(message.from_user.id):
        await message.answer(
            "🔒 **Доступ ограничен!**\n\n"
            "Чтобы пользоваться калькулятором толщины стекла, необходимо подписаться на наш канал **Аквариумная мастерская Reefland**.",
            parse_mode="Markdown",
            reply_markup=get_subscribe_keyboard()
        )
        return

    await message.answer(
        "🛠 **Аквариумная мастерская Reefland**\n\n"
        "Точный расчет толщины стекла для аквариумов (Optiwhite / М1).\n\n"
        "Отправьте размеры: Длина Ширина Высота (см).\n"
        "Пример: `150х60х60` или `150 60 60`",
        parse_mode="Markdown",
        reply_markup=get_start_keyboard()
    )


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer(f"⛔️ Отказано в доступе. Ваш ID: `{message.from_user.id}`", parse_mode="Markdown")
        return

    try:
        total_users, total_calcs, v_stats, top_users = await db_get_stats()

        stats_text = (
            "📈 **Статистика Reefland Bot (Supabase PG):**\n\n"
            f"👥 Уникальных пользователей: **{total_users}**\n"
            f"📐 Всего расчетов: **{total_calcs}**\n\n"
            "💧 **Распределение по объемам:**\n"
            f"• до 50 л: **{v_stats['under_50'][1]}%** ({v_stats['under_50'][0]})\n"
            f"• 50–150 л: **{v_stats['50_150'][1]}%** ({v_stats['50_150'][0]})\n"
            f"• 150–300 л: **{v_stats['150_300'][1]}%** ({v_stats['150_300'][0]})\n"
            f"• от 300 л: **{v_stats['over_300'][1]}%** ({v_stats['over_300'][0]})\n\n"
            "👤 **Список пользователей:**\n"
        )

        if not top_users:
            stats_text += "_Пока никто не пользовался ботом._"
        else:
            user_lines = [f"• {r['name']} ({r['username']}) — расчетов: {r['calculations']}" for r in top_users]
            stats_text += "\n".join(user_lines)

        await message.answer(stats_text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка при сборе статистики: {e}")
        await message.answer(f"⚠️ Ошибка вывода статистики: `{e}`", parse_mode="Markdown")


@dp.callback_query(lambda c: c.data == "check_sub")
async def process_check_sub(callback: types.CallbackQuery):
    await db_register_user(callback.from_user)
    if await check_user_subscription(callback.from_user.id):
        await callback.message.edit_text(
            "🛠 **Аквариумная мастерская Reefland**\n\n"
            "✅ **Спасибо за подписку!** Доступ открыт.\n\n"
            "Точный расчет толщины стекла для аквариумов (Optiwhite / М1).\n\n"
            "Отправьте размеры: Длина Ширина Высота (см).\n"
            "Пример: `150х60х60` или `150 60 60`",
            parse_mode="Markdown",
            reply_markup=get_start_keyboard()
        )
    else:
        await callback.answer("❌ Вы еще не подписались на канал!", show_alert=True)


@dp.message()
async def process_calc(message: types.Message):
    if message.text and message.text.startswith("/"):
        return

    await db_register_user(message.from_user)

    if not await check_user_subscription(message.from_user.id):
        await message.answer(
            "🔒 Чтобы рассчитать толщину стекла, пожалуйста, подпишитесь на наш канал.",
            parse_mode="Markdown",
            reply_markup=get_subscribe_keyboard()
        )
        return

    text = message.text.lower().replace(",", ".").replace("х", " ").replace("x", " ").replace("*", " ").replace("мм", "").strip()
    parts = text.split()

    if len(parts) != 3:
        await message.answer(
            "❌ Укажите 3 числа через пробел или «х»:\n\n"
            "Отправьте размеры: Длина Ширина Высота (см).\n"
            "Пример: `150х60х60` или `150 60 60`",
            parse_mode="Markdown",
            reply_markup=get_start_keyboard()
        )
        return

    try:
        length, width, height = float(parts[0]), float(parts[1]), float(parts[2])

        if length > 300 or width > 300 or height > 300:
            length /= 10.0
            width /= 10.0
            height /= 10.0

        if length <= 0 or width <= 0 or height <= 0:
            await message.answer("⚠️ Все размеры должны быть больше 0.")
            return

        volume_l = int((length * width * height) / 1000)

        await db_increment_calc(message.from_user, volume_l)

        exact, rec, bracing_text = calculate_glass_thickness(length, width, height)

        l_m, w_m, h_m = length / 100.0, width / 100.0, height / 100.0
        area_m2 = (l_m * w_m) + (2 * l_m * h_m) + (2 * w_m * h_m)
        glass_weight_kg = round(area_m2 * rec * 2.5, 1)
        total_weight_kg = int(glass_weight_kg + volume_l)

        res_text = (
            f"🛠 **Аквариумная мастерская Reefland**\n\n"
            f"📐 **Размеры аквариума:** {length:.0f} × {width:.0f} × {height:.0f} см\n"
            f"💧 **Объём:** ~{volume_l} л\n\n"
            f"📊 **Характеристики:**\n"
            f"• Рекомендуемое стекло: **{rec} мм** (Optiwhite или М1)\n"
            f"• Рёбра и стяжки: **{bracing_text}**\n\n"
            f"⚖️ **Вес конструкции:**\n"
            f"• Сухой вес стекла: **~{glass_weight_kg} кг**\n"
            f"• Вес с водой: **~{total_weight_kg} кг** *(без учета декора)*\n\n"
            f"💡 *Расчет выполнен с учетом стандартов надежности мастерской Reefland.*"
        )
        await message.answer(res_text, parse_mode="Markdown", reply_markup=get_result_keyboard(length, width, height, rec))

    except Exception as e:
        logging.error(f"Ошибка при расчете: {e}")
        await message.answer("❌ Произошла ошибка при вычислении. Проверьте правильность введенных чисел.")


async def on_startup(app: web.Application):
    await init_db_pool()
    if bot and WEBHOOK_URL:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
        logging.info(f"Webhook установлен: {WEBHOOK_URL}")


async def handle_ping(request):
    return web.Response(text="OK", status=200)


def main():
    if not BOT_TOKEN:
        logging.error("ОШИБКА: BOT_TOKEN не задан!")
        return

    app = web.Application()
    app.router.add_get("/", handle_ping)

    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)

    logging.info(f"Запуск сервера на порту {PORT}...")
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
