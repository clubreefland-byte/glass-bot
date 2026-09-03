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
BOT_TOKEN = os.getenv("8981341931:AAHm-4nDSzBu7iRpbHj5-i2NLVMhtRxh2Vc")

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher(storage=MemoryStorage())

# --- АЛГОРИТМ РАСЧЕТА ТОЛЩИНЫ СТЕКЛА ---
def calculate_glass_thickness(length_cm: float, height_cm: float) -> tuple[float, int]:
    """
    Расчет минимальной толщины стекла аквариума.
    Возвращает (точную толщину в мм, рекомендуемую стандартную толщину в мм).
    """
    # Допустимое напряжение изгиба для силикатного стекла с коэффициентом k=3.8 (~0.6 кг/мм²)
    sigma_allow = 0.6  
    p = height_cm / 100.0  # Гидростатическое давление на дне (кг/см²)
    
    # Расчет максимального изгибающего момента для стенки
    alpha = 0.00015  # Коэффициент соотношения сторон (L/H)
    ratio = length_cm / height_cm
    if ratio < 1.0:
        alpha = 0.00008
    elif ratio < 1.5:
        alpha = 0.00012
    elif ratio < 2.0:
        alpha = 0.00018
    elif ratio < 3.0:
        alpha = 0.00024
    else:
        alpha = 0.00030

    # Расчет точной толщины (в мм)
    thickness_mm = math.sqrt((alpha * p * (height_cm ** 2)) / sigma_allow) * 10.0
    
    # Добавляем технологический запас +15%
    thickness_mm *= 1.15

    # Подбор ближайшего стандартного номинала стекла
    standard_sizes = [4, 5, 6, 8, 10, 12, 15, 19, 25]
    recommended_size = standard_sizes[-1]
    for size in standard_sizes:
        if size >= thickness_mm:
            recommended_size = size
            break

    return round(thickness_mm, 2), recommended_size

# --- ОБРАБОТЧИКИ ТЕЛЕГРАМ-БОТА ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 **Калькулятор толщины стекла аквариума**\n\n"
        "Отправьте мне размеры бескаркасного аквариума в сантиметрах:\n"
        "**Длина, Ширина, Высота**\n\n"
        "Пример: `100 50 50` или `120, 60, 55`",
        parse_mode="Markdown"
    )

@dp.message()
async def process_calc(message: types.Message):
    text = message.text.replace(",", " ").strip()
    parts = text.split()
    
    if len(parts) != 3:
        await message.answer("❌ Укажите 3 числа: **Длина, Ширина, Высота** (в см).\nПример: `100 50 50`", parse_mode="Markdown")
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
            f"• Рекомендуемое стекло: **{rec} мм** (Optiwhite или силикат)\n\n"
            f"💡 *Расчет выполнен с коэффициентом запаса прочности k=3.8 для бескаркасных аквариумов.*"
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
