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

# Логирование
logging.basicConfig(level=logging.INFO)

# Переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

ADMIN_ID = 1318763491

WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None

PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher(storage=MemoryStorage())

CHANNEL_USERNAME = "@club_reefland"

bot_stats = {
    "users": {},
    "total_calculations": 0
}


async def check_user_subscription(user_id: int) -> bool:
    if not bot:
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        if member.status in ["creator", "administrator", "member"]:
            return True
        return False
    except TelegramBadRequest:
        logging.error("Не удалось проверить подписку.")
        return True 
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        return True


def get_subscribe_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Подписаться на Reefland", 
                    url="https://t.me/club_reefland"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Проверить подписку", 
                    callback_data="check_sub"
                )
            ]
        ]
    )


def get_start_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Канал Reefland", 
                    url="https://t.me/club_reefland"
                )
            ]
        ]
    )


def get_result_keyboard(length, width, height, rec):
    l_int, w_int, h_int, r_int = int(round(length)), int(round(width)), int(round(height)), int(round(rec))
    
    calc_data = f"?text=Здравствуйте!%20Интересует%20стоимость%20изготовления%20аквариума%20{l_int}х{w_int}х{h_int}см%20из%20стекла%20{r_int}мм."

    share_text = quote(
        f"📐 Я рассчитал толщину стекла для аквариума {l_int}×{w_int}×{h_int} см!\n"
        f"Рекомендуемая толщина: {r_int} мм (Optiwhite / М1)."
    )

    share_url = f"https://t.me/share/url?url=https://t.me/AquaGlassCalcBot&text={share_text}"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📩 Узнать стоимость изготовления", 
                    url=f"https://t.me/Asteriy78{calc_data}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📤 Поделиться результатом", 
                    url=share_url
                )
            ],
            [
                InlineKeyboardButton(
                    text="📢 Канал Reefland", 
                    url="https://t.me/club_reefland"
                )
            ]
        ]
    )


# --- ТОЧНАЯ СЕТКА СТАНДАРТОВ МАСТЕРСКОЙ REEFLAND ---
def calculate_glass_thickness(length_cm: float, width_cm: float, height_cm: float) -> tuple[float, int, str]:
    if height_cm <= 0 or length_cm <= 0 or width_cm <= 0:
        raise ValueError("Размеры должны быть больше нуля.")

    l = int(round(length_cm))
    w = int(round(width_cm))
    h = int(round(height_cm))

    # 1. Жесткая база точных стандартов Reefland (Д, Ш, В)
    EXACT_STANDARDS = {
        # Кубическая линейка
        (30, 30, 30): 6, 
        (40, 40, 40): 6, 
        (45, 45, 45): 8, 
        (50, 50, 50): 8,   
        (60, 60, 60): 10,  
        (70, 70, 70): 12,
        (80, 80, 80): 15,
        
        # Прямоугольные стандарты
        (45, 30, 30): 6, (60, 30, 36): 6, (60, 30, 40): 6, 
        (60, 40, 40): 8, (60, 45, 45): 8, (80, 35, 40): 8, 
        (80, 45, 45): 10, (90, 45, 45): 10, (90, 50, 50): 10, (100, 40, 40): 10, (100, 45, 45): 10, 
        (70, 60, 60): 12, (90, 60, 60): 12, (100, 50, 50): 12, (120, 50, 50): 12, (120, 50, 60): 12,
        (120, 60, 60): 15, (150, 60, 50): 15,
        (150, 50, 50): 15, (150, 50, 60): 15, (150, 60, 60): 15, (160, 60, 60): 15,
        (180, 60, 60): 15, (180, 70, 70): 15, (200, 60, 60): 15, (200, 70, 70): 15
    }

    key_direct = (l, w, h)
    key_swapped = (w, l, h)

    if key_direct in EXACT_STANDARDS:
        rec_mm = EXACT_STANDARDS[key_direct]
    elif key_swapped in EXACT_STANDARDS:
        rec_mm = EXACT_STANDARDS[key_swapped]
    else:
        # 2. Правила расчёта для произвольных/нестандартных размеров
        max_side = max(length_cm, width_cm)

        if height_cm <= 35:
            if max_side <= 60: rec_mm = 6
            elif max_side <= 100: rec_mm = 8
            else: rec_mm = 10

        elif height_cm <= 45:
            if max_side <= 60: rec_mm = 6
            elif max_side <= 90: rec_mm = 8
            elif max_side <= 120: rec_mm = 10
            else: rec_mm = 12

        elif height_cm <= 52:
            if max_side <= 55: rec_mm = 8       
            elif max_side <= 100: rec_mm = 10
            elif max_side <= 140: rec_mm = 12
            else: rec_mm = 15

        elif height_cm <= 62:
            if max_side <= 65: rec_mm = 10     
            elif max_side <= 130: rec_mm = 12  
            else: rec_mm = 15                  

        elif height_cm <= 72:
            if max_side <= 130: rec_mm = 15
            else: rec_mm = 15
        else:
            rec_mm = 19

    # Определение требований к рёбрам и стяжкам
    max_side = max(length_cm, width_cm)
    bracing_text = "Не требуются"

    if rec_mm == 15 and height_cm <= 52:
        bracing_text = "Не требуются"
    elif max_side >= 160 or (rec_mm == 15 and max_side >= 150 and height_cm >= 60) or height_cm >= 70:
        bracing_text = "Требуются рёбра жесткости и стяжки"
    elif max_side >= 130 or (height_cm >= 65 and rec_mm < 15):
        bracing_text = "Рекомендуются рёбра жесткости"

    return float(rec_mm), rec_mm, bracing_text


def register_user(user: types.User):
    user_id = user.id
    full_name = user.full_name or "Без имени"
    username = f"@{user.username}" if user.username else "нет username"
    
    if user_id not in bot_stats["users"]:
        bot_stats["users"][user_id] = {
            "name": full_name,
            "username": username,
            "calculations": 0
        }
    else:
        bot_stats["users"][user_id]["name"] = full_name
        bot_stats["users"][user_id]["username"] = username


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    register_user(message.from_user)

    if not await check_user_subscription(user_id):
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
        return

    total_users = len(bot_stats["users"])
    total_calcs = bot_stats["total_calculations"]

    stats_text = (
        "📈 **Статистика использования бота:**\n\n"
        f"👥 Уникальных пользователей: **{total_users}**\n"
        f"📐 Всего расчетов: **{total_calcs}**\n\n"
        "👤 **Список пользователей:**\n"
    )

    if not bot_stats["users"]:
        stats_text += "_Пока никто не пользовался ботом._"
    else:
        user_lines = []
        for uid, data in list(bot_stats["users"].items())[-20:]:
            name = data["name"]
            username = data["username"]
            calcs = data["calculations"]
            user_lines.append(f"• {name} ({username}) — расчетов: {calcs}")
        
        stats_text += "\n".join(user_lines)
        if total_users > 20:
            stats_text += f"\n\n_...и еще {total_users - 20} пользователей._"

    await message.answer(stats_text, parse_mode="Markdown")


@dp.callback_query(lambda c: c.data == "check_sub")
async def process_check_sub(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_user(callback.from_user)
    
    if await check_user_subscription(user_id):
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
    user_id = message.from_user.id
    register_user(message.from_user)

    if not await check_user_subscription(user_id):
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
        length = float(parts[0])
        width = float(parts[1])
        height = float(parts[2])

        # Автоперевод из миллиметров в сантиметры
        if length > 300 or width > 300 or height > 300:
            length /= 10.0
            width /= 10.0
            height /= 10.0

        if length <= 0 or width <= 0 or height <= 0:
            await message.answer("⚠️ Все размеры должны быть больше 0.")
            return

        bot_stats["total_calculations"] += 1
        bot_stats["users"][user_id]["calculations"] += 1

        exact, rec, bracing_text = calculate_glass_thickness(length, width, height)

        volume_l = int((length * width * height) / 1000)
        
        l_m = length / 100.0
        w_m = width / 100.0
        h_m = height / 100.0
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
        await message.answer(
            res_text, 
            parse_mode="Markdown", 
            reply_markup=get_result_keyboard(length, width, height, rec)
        )

    except ValueError as ve:
        await message.answer(f"❌ Ошибка в данных: {ve}")
    except Exception as e:
        logging.error(f"Непредвиденная ошибка при расчете для юзера {user_id}: {e}")
        await message.answer("❌ Произошла ошибка при вычислении. Проверьте правильность введенных чисел.")


async def on_startup(app: web.Application):
    if bot and WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
        logging.info(f"Webhook успешно установлен: {WEBHOOK_URL}")
    else:
        logging.warning("WEBHOOK_URL не задан или бот не инициализирован!")


async def handle_ping(request):
    return web.Response(text="OK", status=200)


def main():
    if not BOT_TOKEN:
        logging.error("ОШИБКА: BOT_TOKEN не задан!")
        return

    app = web.Application()
    app.router.add_get("/", handle_ping)

    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)

    logging.info(f"Запуск веб-сервера на порту {PORT}...")
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
