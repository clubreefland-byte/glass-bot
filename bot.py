import asyncio
import math
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

# Ваш токен от BotFather
BOT_TOKEN = "8981341931:AAGm-4nDSzGu7iRpbIjl5-i2XLMHtRXh2Vc"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# Состояния FSM для пошагового ввода
class TankCalc(StatesGroup):
    waiting_for_length = State()
    waiting_for_width = State()
    waiting_for_height = State()


def calculate_glass_thickness(length_mm: float, width_mm: float, height_mm: float) -> tuple[int, float]:
    """
    Расчет минимальной толщины стекла без ребер и стяжек (Safety Factor >= 3.8).
    Размеры передаются в мм.
    Возвращает: (рекомендуемая толщина в мм, объем в литрах)
    """
    L = length_mm / 1000.0  # Длина в метрах
    H = height_mm / 1000.0  # Высота в метрах
    
    # Объем габаритный (gross)
    volume_liters = (length_mm * width_mm * height_mm) / 1_000_000.0

    # Отношение длины к высоте
    ratio = L / H if H > 0 else 1.0

    # Коэффициент Альфа для расчета изгибающего момента
    if ratio < 0.5:
        alpha = 0.003
    elif ratio <= 3.0:
        alpha = 0.083 * (ratio ** 3) - 0.28 * (ratio ** 2) + 0.35 * ratio - 0.08
        alpha = max(0.003, min(alpha, 0.37))
    else:
        alpha = 0.37

    # Допустимое напряжение для силикатного стекла (19.2 МПа)
    sigma_allowed = 19.2 * 10**6
    density_water = 1000.0
    g = 9.81

    # Расчет толщины в метрах
    p = density_water * g
    t_m = math.sqrt((alpha * p * (H ** 3)) / sigma_allowed)
    t_mm = t_m * 1000.0

    # Стандартная линейка листового стекла
    standard_sizes = [4, 5, 6, 8, 10, 12, 15, 19]
    
    recommended_thickness = standard_sizes[-1]
    for size in standard_sizes:
        if size >= t_mm:
            recommended_thickness = size
            break

    # Дополнительная корректировка для малых высот/объемов
    if height_mm <= 320 and volume_liters <= 40:
        recommended_thickness = max(4, recommended_thickness)
    elif height_mm <= 400 and volume_liters <= 80:
        recommended_thickness = max(5, recommended_thickness)

    return recommended_thickness, volume_liters


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет! Я помогу рассчитать толщину стекла для **открытого аквариума** (без ребер и стяжек).\n\n"
        "Введите **длину** аквариума в миллиметрах (например, 600):"
    )
    await state.set_state(TankCalc.waiting_for_length)


@dp.message(TankCalc.waiting_for_length)
async def process_length(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("Пожалуйста, введите корректное число в миллиметрах (например, 600):")
        return
    
    await state.update_data(length=int(message.text))
    await message.answer("Отлично. Теперь введите **ширину** (глубину) в миллиметрах (например, 350):")
    await state.set_state(TankCalc.waiting_for_width)


@dp.message(TankCalc.waiting_for_width)
async def process_width(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("Пожалуйста, введите корректное число в миллиметрах (например, 350):")
        return

    await state.update_data(width=int(message.text))
    await message.answer("И последнее: введите **высоту** в миллиметрах (например, 360):")
    await state.set_state(TankCalc.waiting_for_height)


@dp.message(TankCalc.waiting_for_height)
async def process_height(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("Пожалуйста, введите корректное число в миллиметрах (например, 360):")
        return

    height = int(message.text)
    user_data = await state.get_data()
    length = user_data['length']
    width = user_data['width']

    thickness, volume = calculate_glass_thickness(length, width, height)

    response_text = (
        f"📊 **Результат расчета:**\n\n"
        f"📏 Размеры: **{length} × {width} × {height} мм**\n"
        f"💧 Габаритный объем: **{volume:.1f} л**\n"
        f"💎 Рекомендуемая толщина стекла: **{thickness} мм**\n\n"
        f"📌 *Расчет выполнен для бескаркасного открытого аквариума без ребер и стяжек (запас прочности 3.8+).* "
        f"Для аквариумов высотой до 40 см рекомендуется использовать полированное стекло (Optiwhite).* "
    )

    await message.answer(response_text, parse_mode="Markdown")
    await message.answer("Чтобы сделать новый расчет, отправьте команду /start")
    await state.clear()


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())