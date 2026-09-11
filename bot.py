import os
import logging
import sqlite3
from urllib.parse import quote
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://glass-bot-pcbh.onrender.com").rstrip("/")

ADMIN_ID = 1318763491
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher(storage=MemoryStorage())

CHANNEL_USERNAME = "@club_reefland"
DB_PATH = "stats.db"

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                username TEXT,
                calculations INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS calculations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                volume_l INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Ошибка БД init: {e}")

init_db()

def db_register_user(user: types.User):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        full_name = user.full_name or "Без имени"
        username = f"@{user.username}" if user.username else "нет username"
        cursor.execute("""
            INSERT INTO users (user_id, name, username, calculations)
            VALUES (?, ?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, username=excluded.username
        """, (user.id, full_name, username))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Ошибка регистрации БД: {e}")

def db_increment_calc(user: types.User, volume_l: int):
    try:
        db_register_user(user)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET calculations = calculations + 1 WHERE user_id = ?", (user.id,))
        cursor.execute("INSERT INTO calculations (user_id, volume_l) VALUES (?, ?)", (user.id, volume_l))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Ошибка инкремента БД: {e}")

async def check_user_subscription(user_id: int) -> bool:
    if not bot:
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
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

def get_intent_keyboard(l: int, w: int, h: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏢 Хочу заказать аквариум в Reefland", callback_data=f"o_{int(l)}_{int(w)}_{int(h)}")],
            [InlineKeyboardButton(text="🛠 Делаю сам / Сравниваю параметры", callback_data=f"d_{int(l)}_{int(w)}_{int(h)}")]
        ]
    )

def get_result_keyboard(length: int, width: int, height: int, rec: int):
    calc_text = f"Здравствуйте! Интересует стоимость изготовления аквариума {length}х{width}х{height}см из стекла {rec}мм (Optiwhite)."
    lead_url = f"https://t.me/Asteriy78?text={quote(calc_text)}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Рассчитать стоимость сборки под ключ", url=lead_url)],
            [InlineKeyboardButton(text="📢 Канал Reefland", url="https://t.me/club_reefland")]
        ]
    )

def calculate_glass_thickness(length_cm: float, width_cm: float, height_cm: float) -> tuple[float, int, str]:
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

    if (l, w, h) in EXACT_STANDARDS: rec_mm = EXACT_STANDARDS[(l, w, h)]
    elif (w, l, h) in EXACT_STANDARDS: rec_mm = EXACT_STANDARDS[(w, l, h)]
    else:
        max_side = max(length_cm, width_cm)
        if height_cm <= 35: rec_mm = 6 if max_side <= 60 else (8 if max_side <= 100 else 10)
        elif height_cm <= 45: rec_mm = 6 if max_side <= 60 else (8 if max_side <= 90 else (10 if max_side <= 120 else 12))
        elif height_cm <= 52: rec_mm = 8 if max_side <= 55 else (10 if max_side <= 100 else (12 if max_side <= 140 else 15))
        elif height_cm <= 62: rec_mm = 10 if max_side <= 65 else (12 if max_side <= 130 else 15)
        elif height_cm <= 72: rec_mm = 15
        else: rec_mm = 19

    max_side = max(length_cm, width_cm)
    bracing_text = "Не требуются"
    if rec_mm == 15 and height_cm <= 52 and max_side <= 160: bracing_text = "Не требуются"
    elif max_side > 160 or (rec_mm == 15 and max_side >= 150 and height_cm >= 60) or height_cm >= 70:
        bracing_text = "Требуются рёбра жесткости и стяжки"
    elif max_side >= 130 or (height_cm >= 65 and rec_mm < 15):
        bracing_text = "Рекомендуются рёбра жесткости"

    return float(rec_mm), rec_mm, bracing_text

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    db_register_user(message.from_user)
    if not await check_user_subscription(message.from_user.id):
        await message.answer("🔒 <b>Доступ ограничен!</b>\n\nПодпишитесь на канал <b>Аквариумная мастерская Reefland</b>.", parse_mode="HTML", reply_markup=get_subscribe_keyboard())
        return
    await message.answer("🛠 <b>Аквариумная мастерская Reefland</b>\n\nОтправьте размеры: Длина Ширина Высота (см).\nПример: <code>150х60х60</code>", parse_mode="HTML")

@dp.callback_query(F.data == "check_sub")
async def process_check_sub(callback: types.CallbackQuery):
    await callback.answer()
    if await check_user_subscription(callback.from_user.id):
        await bot.send_message(chat_id=callback.from_user.id, text="🛠 <b>Аквариумная мастерская Reefland</b>\n\n✅ Доступ открыт.\nОтправьте размеры: Длина Ширина Высота (см).", parse_mode="HTML")
    else:
        await callback.answer("❌ Вы еще не подписались на канал!", show_alert=True)

@dp.message()
async def process_calc_input(message: types.Message):
    if message.text and message.text.startswith("/"): return
    db_register_user(message.from_user)

    if not await check_user_subscription(message.from_user.id):
        await message.answer("🔒 Подпишитесь на канал для использования бота.", reply_markup=get_subscribe_keyboard())
        return

    text = message.text.lower().replace(",", ".").replace("х", " ").replace("x", " ").replace("*", " ").replace("мм", "").strip()
    parts = text.split()

    if len(parts) != 3:
        await message.answer("❌ Укажите 3 числа: Длина Ширина Высота (см).\nПример: <code>150х60х60</code>", parse_mode="HTML")
        return

    try:
        l, w, h = float(parts[0]), float(parts[1]), float(parts[2])
        if l > 300 or w > 300 or h > 300: 
            l, w, h = l / 10.0, w / 10.0, h / 10.0
        if l <= 0 or w <= 0 or h <= 0: return

        l_int, w_int, h_int = int(round(l)), int(round(w)), int(round(h))
        await message.answer(
            f"📐 Размеры: <b>{l_int}×{w_int}×{h_int} см</b> (~{int((l_int*w_int*h_int)/1000)} л)\n\nУточните цель расчета:",
            parse_mode="HTML", reply_markup=get_intent_keyboard(l_int, w_int, h_int)
        )
    except ValueError:
        await message.answer("❌ Ошибка ввода. Введите три числа через пробел.")

# Обработка нажатий на инлайн-кнопки
@dp.callback_query(F.data.startswith("o_") | F.data.startswith("d_"))
async def process_calc_choice(callback: types.CallbackQuery):
    # Сразу снимаем задержку "часиков" с кнопки
    await callback.answer()

    data = callback.data
    user_id = callback.from_user.id

    try:
        parts = data.split("_")
        action = parts[0]
        length = int(float(parts[1]))
        width = int(float(parts[2]))
        height = int(float(parts[3]))

        volume_l = int((length * width * height) / 1000)
        db_increment_calc(callback.from_user, volume_l)
        exact, rec, bracing_text = calculate_glass_thickness(length, width, height)

        l_m, w_m, h_m = length / 100.0, width / 100.0, height / 100.0
        area_m2 = (l_m * w_m) + (2 * l_m * h_m) + (2 * w_m * h_m)
        glass_weight_kg = round(area_m2 * rec * 2.5, 1)
        total_weight_kg = int(glass_weight_kg + volume_l)

        if action == "o":
            res_text = (
                f"🛠 <b>Аквариумная мастерская Reefland</b>\n\n"
                f"📐 <b>Проект аквариума:</b> {length} × {width} × {height} см\n"
                f"💧 <b>Объём:</b> ~{volume_l} л\n\n"
                f"📊 <b>Спецификация Reefland:</b>\n"
                f"• Рекомендуемое стекло: <b>{rec} мм</b> (Optiwhite M1)\n"
                f"• Рёбра и стяжки: <b>{bracing_text}</b>\n"
                f"• Вес стекла: <b>~{glass_weight_kg} кг</b> | С водой: <b>~{total_weight_kg} кг</b>\n\n"
                f"💡 <i>В стоимость входит полировка еврокромки и сборка на высокопрочный силикон.</i>"
            )
            await bot.send_message(
                chat_id=user_id,
                text=res_text,
                parse_mode="HTML",
                reply_markup=get_result_keyboard(length, width, height, rec)
            )

            try:
                user_info = f"@{callback.from_user.username}" if callback.from_user.username else f"ID: {callback.from_user.id}"
                await bot.send_message(
                    ADMIN_ID,
                    f"🔥 <b>ЗАЯВКА!</b>\n\nКлиент: {callback.from_user.full_name} ({user_info})\nРазмеры: {length}×{width}×{height} см",
                    parse_mode="HTML"
                )
            except Exception as e:
                logging.error(f"Ошибка отправки админу: {e}")

        else:
            res_text = (
                f"📐 <b>Базовый расчёт толщины:</b>\n\n"
                f"Размеры: {length} × {width} × {height} см\n"
                f"Минимальная толщина стекла: <b>{rec} мм</b>"
            )
            await bot.send_message(
                chat_id=user_id,
                text=res_text,
                parse_mode="HTML"
            )

    except Exception as e:
        logging.error(f"❌ Ошибка в обработчике Callback: {e}")

async def on_startup(app: web.Application):
    if bot and WEBHOOK_URL:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
        logging.info(f"УСПЕШНО УСТАНОВЛЕН WEBHOOK: {WEBHOOK_URL}")

async def handle_ping(request):
    return web.Response(text="OK", status=200)

def main():
    if not BOT_TOKEN: return
    app = web.Application()
    app.router.add_get("/", handle_ping)
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
