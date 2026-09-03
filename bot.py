import asyncio
import os
import logging
import math
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

# Логирование для отслеживания статуса на Render
logging.basicConfig(level=logging.INFO)

# Токен безопасно забирается из Environment Variables в Render
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher(storage=MemoryStorage())

# --- АЛГОРИТМ РАСЧЕТА ТОЛЩИНЫ СТЕКЛА ---
def calculate_glass_thickness(length_cm: float, height_cm: float) -> tuple[float, int]:
    """
    Расчет толщины стекла бескаркасного аквариума без стяжек/ребер.
    Учитывает изгибающий момент и прогиб длинной стенки.
    """
    # Допустимое напряжение изгиба для силикатного / Optiwhite стекла
    sigma = 16.0  # МПа
    p = height_cm * 0.00981  # Гидростатическое давление воды на дне (МПа)
    
    # Коэффициент формы (соотношение длины к высоте)
    ratio = length_cm / height_cm
    
    # Коэффициент изгибающего момента alpha
    if ratio <= 1.0:
        alpha = 0.030
    elif ratio <= 1.5:
        alpha = 0.045
    elif ratio <= 2.0:
        alpha = 0.062
    elif ratio <= 2.5:
        alpha = 0.075
    elif ratio <= 3.0:
        alpha = 0.083
    else:
        alpha = 0.090

    # Точный расчет толщины (мм)
    exact_mm = math.sqrt((alpha * p * (height_cm ** 2)) / sigma) * 10.0
    
    # Корректировка на прогиб для длинных аквариумов от 120 см
    if length_cm >= 120 and height_cm >= 50:
        exact_mm = max(exact_mm, 10.8)  # Попадает в номинал 12 мм
    elif length_cm >= 150:
        exact_mm = max(exact_mm, 13.5)  # Попадает в номинал 15 мм

    # Стандартные номиналы полированного стекла
    standard_sizes = [4, 5, 6, 8, 10, 12, 15, 19, 25]
    recommended_size = standard_sizes[-1]
    for size in standard_sizes:
        if size >= exact_mm:
            recommended_size = size
            break

    return round(exact_mm, 2), recommended_size

# --- ОБРАБОТЧИКИ ТЕЛЕГРАМ-БОТА ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 **Калькулятор толщины стекла аквариума**\n\n"
        "Отправьте размеры бескаркасного аквариума в сантиметрах:\n"
        "**Длина, Ширина, Высота**\n\n"
        "Пример: `100 50 50` или `120 50 50`",
        parse_mode="Markdown"
    )

@dp.message()
async def process_calc(message: types.Message):
    text = message.text.replace(",", " ").strip()
    parts = text.split()
    
    if len(parts) != 3:
        await message.answer("❌ Укажите 3 числа: **Длина, Ширина, Высота** (в см).\nПример: `120 50 50`", parse_mode="Markdown")
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
            f"💡 *Расчет рассчитан на бескаркасную сборку без стяжек и ребер жесткости.*"
        )
        await message.answer(res_text, parse_mode="Markdown")

    except ValueError:
        await message.answer("❌ Ошибка ввода. Используйте только числа.")

# --- ВЕБ-СЕРВЕР ДЛЯ HEALTH CHECK НА RENDER ---
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
