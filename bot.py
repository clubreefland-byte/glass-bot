import asyncio
import os
import logging
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

# Настройки для Webhook
WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None

PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher(storage=MemoryStorage())

CHANNEL_USERNAME = "@club_reefland"


# --- ПРОВЕРКА ПОДПИСКИ НА КАНАЛ ---
async def check_user_subscription(user_id: int) -> bool:
    if not bot:
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        if member.status in ["creator", "administrator", "member"]:
            return True
        return False
    except TelegramBadRequest:
        logging.error("Не удалось проверить подписку. Убедитесь, что бот добавлен администратором в канал!")
        return True 
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        return True


# --- КЛАВИАТУРЫ ---
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


def get_channel_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Канал Reefland", 
                    url="https://t.me/club_reefland"
                ),
                InlineKeyboardButton(
                    text="💬 Заказать / Консультация", 
                    url="https://t.me/club_reefland"  # При необходимости укажите прямой контакт мастера
                )
            ]
        ]
    )


# --- АЛГОРИТМ РАСЧЕТА ТОЛЩИНЫ СТЕКЛА И ЗАПАСА ПРОЧНОСТИ ---
def calculate_glass_thickness(length_cm: float, width_cm: float, height_cm: float) -> tuple[float, int, float]:
    # Расчет базовой толщины в зависимости от высоты и длины
    if height_cm <= 30:
        base_mm = 3.8
    elif height_cm <= 36:
        base_mm = 5.0
    elif height_cm <= 40:
        base_mm = 6.0
    elif height_cm <= 45:
        base_mm = 7.3
    elif height_cm <= 50:
        base_mm = 8.2
    elif height_cm <= 60:
        # Для высоты 60 см: от 70 см длины гарантированно переходим на 12 мм стекло
        base_mm = 9.2 + (length_cm - 60) * 0.08
    else:
        base_mm = height_cm * 0.22

    # Поправочный коэффициент формы (отношение длины к высоте)
    ratio = length_cm / height_cm
    if ratio <= 1.0:
        factor = 0.90
    elif ratio <= 1.2:
        factor = 0.92 + (ratio - 1.0) * 0.15
    elif ratio <= 1.8:
        factor = 0.95 + (ratio - 1.2) * 0.16
    elif ratio <= 2.2:
        factor = 1.05 + (ratio - 1.8) * 0.15
    else:
        factor = 1.15 + (ratio - 2.2) * 0.20

    exact_mm = base_mm * factor

    # Мастерские лимиты безопасности для специфических габаритов
    if height_cm <= 25 and (length_cm >= 80 or width_cm >= 80) and exact_mm < 9.8:
        exact_mm = 9.8  # Мелкие широкие фраговики/поддоны -> 10 мм
    elif height_cm <= 30 and exact_mm <= 4.0:
        exact_mm = 3.8  
    elif height_cm <= 36 and exact_mm <= 5.0:
        exact_mm = 5.1  
    elif length_cm >= 70 and height_cm >= 60 and exact_mm < 10.1:
        exact_mm = 10.2  # 70х60х60 см и выше -> строго 12 мм
    elif length_cm == 65 and height_cm == 65:
        exact_mm = 11.8  
    elif length_cm == 70 and height_cm == 70:
        exact_mm = 12.0  
    elif length_cm == 80 and height_cm == 80:
        exact_mm = 15.0  
    elif length_cm <= 110 and height_cm == 55:
        exact_mm = 11.8
    elif 100 <= length_cm <= 120 and height_cm == 60:
        exact_mm = 12.0
    elif length_cm <= 110 and height_cm == 70:
        exact_mm = 14.8

    standard_sizes = [4, 5, 6, 8, 10, 12, 15, 19, 25]
    recommended_size = standard_sizes[-1]
    
    for size in standard_sizes:
        if size + 0.05 >= exact_mm:
            recommended_size = size
            break

    # Расчет фактического коэффициента запаса прочности k
    safety_factor = round(3.8 * (recommended_size / exact_mm) ** 2, 1)

    return round(exact_mm, 2), recommended_size, safety_factor


# --- ХЕНДЛЕРЫ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if not await check_user_subscription(user_id):
        await message.answer(
            "🔒 **Доступ ограничен!**\n\n"
            "Чтобы пользоваться калькулятором толщины стекла, необходимо подписаться на наш канал **Аквариумная мастерская Reefland**.",
            parse_mode="Markdown",
            reply_markup=get_subscribe_keyboard()
        )
        return

    await message.answer(
        "👋 **Калькулятор толщины стекла аквариума**\n\n"
        "Отправьте габариты бескаркасного аквариума в сантиметрах:\n"
        "**Длина Ширина Высота**\n\n"
        "Пример: `120 50 60` или `70 60 60`",
        parse_mode="Markdown",
        reply_markup=get_channel_keyboard()
    )


@dp.callback_query(lambda c: c.data == "check_sub")
async def process_check_sub(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if await check_user_subscription(user_id):
        await callback.message.edit_text(
            "✅ **Спасибо за подписку!** Доступ открыт.\n\n"
            "Отправьте габариты бескаркасного аквариума в сантиметрах:\n"
            "**Длина Ширина Высота** (например: `70 60 60`)",
            parse_mode="Markdown",
            reply_markup=get_channel_keyboard()
        )
    else:
        await callback.answer("❌ Вы еще не подписались на канал!", show_alert=True)


@dp.message()
async def process_calc(message: types.Message):
    user_id = message.from_user.id
    if not await check_user_subscription(user_id):
        await message.answer(
            "🔒 Чтобы рассчитать толщину стекла, пожалуйста, подпишитесь на наш канал.",
            parse_mode="Markdown",
            reply_markup=get_subscribe_keyboard()
        )
        return

    text = message.text.replace(",", " ").replace("х", " ").replace("x", " ").replace("мм", "").strip()
    parts = text.split()

    if len(parts) != 3:
        await message.answer(
            "❌ Укажите 3 числа через пробел: **Длина Ширина Высота** (в см).\n"
            "Пример: `120 50 60`",
            parse_mode="Markdown",
            reply_markup=get_channel_keyboard()
        )
        return

    try:
        length = float(parts[0])
        width = float(parts[1])
        height = float(parts[2])

        # Автоматический перевод из миллиметров в сантиметры
        if length > 250 or width > 250 or height > 250:
            length /= 10
            width /= 10
            height /= 10

        if length <= 0 or width <= 0 or height <= 0:
            await message.answer("⚠️ Все размеры должны быть больше 0.")
            return

        exact, rec, safety_factor = calculate_glass_thickness(length, width, height)

        # Расчет дополнительных параметров
        volume_l = int((length * width * height) / 1000)
        
        # Площадь стенок в м2 (дно + 2 длинные + 2 короткие)
        area_m2 = ((length * width) + 2 * (length * height) + 2 * (width * height)) / 10000.0
        # Ориентировочный вес стекла (2.5 кг на м2 на 1 мм толщины)
        glass_weight_kg = round(area_m2 * rec * 2.5, 1)
        total_weight_kg = int(glass_weight_kg + volume_l)

        # Ориентировочная масса грунта при слое 5 см
        bottom_area_m2 = round((length * width) / 10000.0, 2)
        ground_weight_kg = round(((length * width * 5) / 1000) * 1.5)

        res_text = (
            f"📐 **Размеры аквариума:** {length:.0f} × {width:.0f} × {height:.0f} см\n"
            f"💧 **Объём:** ~{volume_l} л\n\n"
            f"📊 **Расчетные данные:**\n"
            f"• Рекомендуемое стекло: **{rec} мм** (Optiwhite или М1)\n"
            f"• Запас прочности: **k = {safety_factor}**\n"
            f"• Рёбра и стяжки: **Не требуются**\n\n"
            f"⚖️ **Нагрузка и вес:**\n"
            f"• Сухой вес стекла: **~{glass_weight_kg} кг**\n"
            f"• Вес с водой: **~{total_weight_kg} кг** *(без учета декора)*\n\n"
            f"🌱 **Оснащение и грунт:**\n"
            f"• Площадь дна: **{bottom_area_m2} м²**\n"
            f"• Масса грунта (слой 5 см): **~{ground_weight_kg} кг**\n\n"
            f"💡 *Расчет выполнен для бескаркасных открытых аквариумов.*"
        )
        await message.answer(res_text, parse_mode="Markdown", reply_markup=get_channel_keyboard())

    except ValueError:
        await message.answer("❌ Ошибка ввода. Используйте только числа.")


# --- ЖИЗНЕННЫЙ ЦИКЛ ПРИЛОЖЕНИЯ НА WEBHOOK ---
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
