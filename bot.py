import asyncio
import os
import logging
from datetime import datetime
from urllib.parse import quote
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# Логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BOT_TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
ADMIN_ID = 1318763491

WEBHOOK_PATH = f"/bot/{BOT_TOKEN}" if BOT_TOKEN else "/bot/webhook"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher(storage=MemoryStorage())

CHANNEL_USERNAME = "@club_reefland"

bot_stats = {
    "users": {},
    "total_calculations": 0,
    "lead_clicks": 0,
    "share_clicks": 0,
    "popular_sizes": {}
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
    l_val = length / 10.0 if length > 300 else length
    w_val = width / 10.0 if width > 300 else width
    h_val = height / 10.0 if height > 300 else height

    lead_payload = f"ld_{int(round(l_val))}_{int(round(w_val))}_{int(round(h_val))}_{int(round(rec))}"
    share_payload = f"sh_{int(round(l_val))}_{int(round(w_val))}_{int(round(h_val))}_{int(round(rec))}"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📩 Узнать стоимость изготовления", callback_data=lead_payload)],
            [InlineKeyboardButton(text="📤 Поделиться результатом", callback_data=share_payload)],
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
        (120, 60, 60): 15, (150, 60, 50): 15, (150, 50, 50): 15, (150, 50, 60): 15, 
        (150, 60, 60): 15, (160, 60, 60): 15, (170, 60, 50): 15, (170, 60, 60): 15, 
        (180, 60, 50): 15, (180, 60, 60): 15, (180, 70, 70): 15, (200, 60, 60): 15, (200, 70, 70): 15
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
        else:
            rec_mm = 15 if height_cm <= 72 else 19

    max_side = max(length_cm, width_cm)
    bracing_text = "Не требуются"
    if rec_mm == 15 and height_cm <= 52 and max_side <= 150:
        bracing_text = "Не требуются"
    elif max_side >= 160 or (rec_mm == 15 and max_side >= 150 and height_cm >= 60) or height_cm >= 70:
        bracing_text = "Требуются рёбра жесткости и стяжки"
    elif max_side >= 130 or (height_cm >= 65 and rec_mm < 15):
        bracing_text = "Рекомендуются рёбра жесткости"

    return float(rec_mm), rec_mm, bracing_text


def register_user(user: types.User):
    if not user:
        return
    user_id = user.id
    if user_id not in bot_stats["users"]:
        bot_stats["users"][user_id] = {
            "name": user.full_name or "Без имени",
            "username": f"@{user.username}" if user.username else "нет username",
            "calculations": 0,
            "last_seen": datetime.now().strftime("%d.%m.%Y")
        }
    else:
        bot_stats["users"][user_id]["name"] = user.full_name or "Без имени"
        bot_stats["users"][user_id]["last_seen"] = datetime.now().strftime("%d.%m.%Y")


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    register_user(message.from_user)
    if not await check_user_subscription(message.from_user.id):
        await message.answer(
            "🔒 **Доступ ограничен!** Подпишитесь на канал **Аквариумная мастерская Reefland**.",
            parse_mode="Markdown",
            reply_markup=get_subscribe_keyboard()
        )
        return
    await message.answer(
        "🛠 **Аквариумная мастерская Reefland**\n\nОтправьте размеры: Длина Ширина Высота (см).\nПример: `150х60х60`",
        parse_mode="Markdown",
        reply_markup=get_start_keyboard()
    )


@dp.callback_query(F.data == "check_sub")
async def process_check_sub(callback: types.CallbackQuery):
    register_user(callback.from_user)
    if await check_user_subscription(callback.from_user.id):
        await callback.message.edit_text(
            "✅ **Спасибо за подписку!** Доступ открыт.\nОтправьте размеры: Длина Ширина Высота (см).",
            parse_mode="Markdown",
            reply_markup=get_start_keyboard()
        )
    else:
        await callback.answer("❌ Вы еще не подписались на канал!", show_alert=True)


@dp.callback_query(F.data.startswith("ld_"))
async def process_lead_click(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    l, w, h, rec = (parts[1], parts[2], parts[3], parts[4]) if len(parts) >= 5 else ("150", "60", "60", "15")
    bot_stats["lead_clicks"] = bot_stats.get("lead_clicks", 0) + 1
    target_url = f"https://t.me/Asteriy78?text=Здравствуйте!%20Интересует%20аквариум%20{l}х{w}х{h}см,%20{rec}мм."
    await callback.answer()
    await callback.message.answer(
        "👍 **Заявка зафиксирована!** Нажмите на кнопку ниже:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Написать мастеру", url=target_url)]]),
        parse_mode="Markdown"
    )


@dp.callback_query(F.data.startswith("sh_"))
async def process_share_click(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    l, w, h, rec = (parts[1], parts[2], parts[3], parts[4]) if len(parts) >= 5 else ("150", "60", "60", "15")
    bot_stats["share_clicks"] = bot_stats.get("share_clicks", 0) + 1
    share_text = quote(f"📐 Рассчитал аквариум {l}×{w}×{h} см, стекло {rec} мм (Reefland).")
    share_url = f"https://t.me/share/url?url=https://t.me/AquaGlassCalcBot&text={share_text}"
    await callback.answer()
    await callback.message.answer(
        "📤 **Переслать результат:**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📲 Отправить в Telegram", url=share_url)]]),
        parse_mode="Markdown"
    )


@dp.message()
async def process_calc(message: types.Message):
    if not message.text:
        return
    register_user(message.from_user)

    if not await check_user_subscription(message.from_user.id):
        await message.answer("🔒 Подпишитесь на канал для доступа к расчетам.", reply_markup=get_subscribe_keyboard())
        return

    text = message.text.lower().replace(",", ".").replace("х", " ").replace("x", " ").replace("*", " ").replace("мм", "").strip()
    parts = text.split()

    if len(parts) != 3:
        await message.answer("❌ Укажите 3 числа: Длина Ширина Высота (см). Пример: `150 60 60`", parse_mode="Markdown")
        return

    try:
        length, width, height = float(parts[0]), float(parts[1]), float(parts[2])
        if length > 300 or width > 300 or height > 300:
            length, width, height = length / 10.0, width / 10.0, height / 10.0

        if length <= 0 or width <= 0 or height <= 0:
            await message.answer("⚠️ Все размеры должны быть больше 0.")
            return

        _, rec, bracing_text = calculate_glass_thickness(length, width, height)
        bot_stats["total_calculations"] += 1
        bot_stats["users"][message.from_user.id]["calculations"] += 1

        volume_l = int((length * width * height) / 1000)
        area_m2 = ((length/100)*(width/100)) + (2*(length/100)*(height/100)) + (2*(width/100)*(height/100))
        glass_weight = round(area_m2 * rec * 2.5, 1)

        res_text = (
            f"🛠 **Аквариумная мастерская Reefland**\n\n"
            f"📐 **Размеры:** {length:.0f} × {width:.0f} × {height:.0f} см\n"
            f"💧 **Объём:** ~{volume_l} л\n"
            f"• Рекомендуемое стекло: **{rec} мм** (Optiwhite / М1)\n"
            f"• Рёбра и стяжки: **{bracing_text}**\n"
            f"• Сухой вес стекла: **~{glass_weight} кг**"
        )
        await message.answer(res_text, parse_mode="Markdown", reply_markup=get_result_keyboard(length, width, height, rec))
    except Exception as e:
        logging.error(f"Ошибка расчета: {e}")
        await message.answer("❌ Ошибка при вычислении. Проверьте числа.")


async def on_startup(app: web.Application):
    if bot and WEBHOOK_URL:
        # Сбрасываем старые вебхуки и ставим новый
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
        logging.info(f"Webhook успешно установлен на адрес: {WEBHOOK_URL}")
    else:
        logging.error("КРИТИЧЕСКИ ОШИБКА: RENDER_EXTERNAL_URL или BOT_TOKEN не заданы!")


async def handle_ping(request):
    return web.Response(text="Bot is alive!", status=200)


def main():
    if not BOT_TOKEN:
        logging.error("ОШИБКА: BOT_TOKEN не найден в переменных окружения!")
        return

    app = web.Application()
    app.router.add_get("/", handle_ping)

    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)

    logging.info(f"Запуск aiohttp сервера на порту {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
