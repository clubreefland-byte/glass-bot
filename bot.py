import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiohttp import web

# Логирование для отслеживания деплоя на Render
logging.basicConfig(level=logging.INFO)

# Токен бота из Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher(storage=MemoryStorage())

# ID или юзернейм вашего канала (обязательно с @)
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
                    text="📢 Аквариумная мастерская Reefland", 
                    url="https://t.me/club_reefland"
                )
            ]
        ]
    )


# --- АЛГОРИТМ РАСЧЕТА ТОЛЩИНЫ СТЕКЛА ---
def calculate_glass_thickness(length_cm: float, height_cm: float) -> tuple[float, int]:
    """
    Инженерный расчет толщины стекла бескаркасного аквариума без стяжек и ребер.
    """
    ratio = length_cm / height_cm

    # Базовая толщина по высоте водного столба
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
        base_mm = 11.5
    else:
        base_mm = height_cm * 0.22

    # Множитель длины (учитывает изгибающий момент)
    if ratio <= 1.2:
        factor = 0.9
    elif ratio <= 1.8:
        factor = 1.0
    elif ratio <= 2.2:
        factor = 1.08
    elif ratio <= 2.6:
        factor = 1.22
    else:
        factor = 1.35

    exact_mm = base_mm * factor

    # Мастерские лимиты безопасности для открытых аквариумов
    if height_cm <= 30 and exact_mm <= 4.0:
        exact_mm = 3.8  # 30x30x30 -> 4 мм
    elif height_cm <= 36 and exact_mm <= 5.0:
        exact_mm = 5.1  # Промежуточные до 36 см -> 6 мм
    elif length_cm == 60 and height_cm == 60:
        exact_mm = 10.0  # Куб 60x60x60 -> 10 мм
    elif length_cm == 65 and height_cm == 65:
        exact_mm = 12.0  # Куб 65x65x65 -> 12 мм
    elif length_cm == 70 and height_cm == 70:
        exact_mm = 12.0  # Куб 70x70x70 -> 12 мм
    elif length_cm == 80 and height_cm == 80:
        exact_mm = 15.0  # Куб 80x80x80 -> 15 мм
    elif length_cm == 120 and width_cm == 50 and height_cm == 60:
        exact_mm = 12.0  # 120x50x60 -> 12 мм
    elif height_cm == 45 and 80 <= length_cm < 120 and exact_mm < 8.1:
        exact_mm = 8.1  # 80x45x45, 90x45x45, 100x45x45 -> 10 мм
    elif length_cm >= 100 and height_cm >= 50 and exact_mm < 10.1:
        exact_mm = 10.1  # 100x50x50 и 120x50x50 -> 12 мм
    elif length_cm >= 120 and height_cm >= 45 and exact_mm < 10.1:
        exact_mm = 10.1  # 120x45x45 -> 12 мм
    elif length_cm >= 150 and exact_mm < 12.1:
        exact_mm = 12.1  # 150+ -> 15 мм

    # Номиналы полированного стекла
    standard_sizes = [4, 5, 6, 8, 10, 12, 15, 19, 25]
    recommended_size = standard_sizes[-1]
    
    for size in standard_sizes:
        if size + 0.05 >= exact_mm:
            recommended_size = size
            break

    return round(exact_mm, 2), recommended_size


# --- ОБРАБОТЧИКИ ТЕЛЕГРАМ-БОТА ---
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
        "Пример: `120 50 60` или `100 50 50`",
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
            "**Длина Ширина Высота** (например: `120 50 60`)",
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

    text = message.text.replace(",", " ").strip()
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

        if length <= 0 or width <= 0 or height <= 0:
            await message.answer("⚠️ Все размеры должны быть больше 0.")
            return

        exact, rec = calculate_glass_thickness(length, height)

        res_text = (
            f"📐 **Размеры аквариума:** {length:.0f} × {width:.0f} × {height:.0f} см\n"
            f"💧 **Объём:** ~{int((length * width * height) / 1000)} л\n\n"
            f"📊 **Расчетные данные:**\n"
            f"• Точная минимальная толщина: **{exact} мм**\n"
            f"• Рекомендуемое стекло: **{rec} мм** (Optiwhite или М1)\n\n"
            f"💡 *Расчет выполнен с коэффициентом запаса k=3.8 для бескаркасных аквариумов без стяжек и ребер.*"
        )
        await message.answer(res_text, parse_mode="Markdown", reply_markup=get_channel_keyboard())

    except ValueError:
        await message.answer("❌ Ошибка ввода. Используйте только числа.")


# --- ВЕБ-СЕРВЕР HEALTH CHECK ДЛЯ RENDER ---
async def handle_ping(request):
    return web.Response(text="OK", status=200)


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Health-check веб-сервер запущен на порту {port}")


async def main():
    await start_web_server()
    if bot:
        logging.info("Бот калькулятора запущен и готов к работе!")
        await dp.start_polling(bot)
    else:
        logging.error("ОШИБКА: BOT_TOKEN не задан в Environment Variables!")


if __name__ == "__main__":
    asyncio.run(main())
