import asyncio
import logging
import re
import sys
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from google import genai
from google.genai import types as genai_types

# Токены (замените на свои или настройте через переменные окружения)
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
ADMIN_USERNAME = "Asteriy78"
CHANNEL_ID = "@club_reefland"

# Инициализация Gemini
ai_client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = (
    "Ты — официальный умный помощник аквариумной мастерской Reefland. "
    "Отвечай экспертно, вежливо и понятно на вопросы по аквариумистике, "
    "уходу за растениями (анубиасы, папоротники), выбору стекла (Optiwhite, М1) "
    "и запуску аквариумов. Если уместно, мягко предлагай обратиться к мастеру "
    "для заказа индивидуального аквариума."
)

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
router = Router()

# Хранилище статистики
user_stats = {}


def check_sub_keyboard():
  return InlineKeyboardMarkup(
      inline_keyboard=[[
          InlineKeyboardButton(
              text="📢 Подписаться на канал", url="https://t.me/club_reefland"
          )
      ]]
  )


def get_result_keyboard(length, width, height, rec):
  l_int, w_int, h_int, r_int = (
      int(round(length)),
      int(round(width)),
      int(round(height)),
      int(round(rec)),
  )
  # Ссылка с обычными пробелами вместо %20
  calc_data = f"?text=Здравствуйте! Интересует стоимость изготовления аквариума {l_int}х{w_int}х{h_int}см из стекла {r_int}мм."

  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="📩 Узнать стоимость изготовления",
                  url=f"https://t.me/{ADMIN_USERNAME}{calc_data}",
              )
          ],
          [
              InlineKeyboardButton(
                  text="📢 Канал Reefland", url="https://t.me/club_reefland"
              )
          ],
      ]
  )


async def check_subscription(bot: Bot, user_id: int) -> bool:
  try:
    member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
    return member.status in ["creator", "administrator", "member"]
  except Exception:
    return False


@router.message(CommandStart())
async def cmd_start(message: types.Message):
  await message.answer(
      "👋 Привет! Я бот-помощник аквариумной мастерской Reefland.\n\n"
      "📐 **Калькулятор стекла:** отправьте размеры в формате `ДлинахШиринахВысота` (например, `100x45x45`).\n"
      "🤖 **ИИ-справочник:** задайте мне любой вопрос по уходу за аквариумом, растениям или оборудованию."
  )


@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
  total_users = len(user_stats)
  total_calcs = sum(data["calcs"] for data in user_stats.values())

  stats_text = (
      f"📊 Статистика использования бота:\n\n"
      f"👥 Уникальных пользователей: {total_users}\n"
      f"📐 Всего расчетов: {total_calcs}\n\n"
      f"👤 Список пользователей:\n"
  )
  for user_id, data in user_stats.items():
    uname = f"(@{data['username']})" if data["username"] else "(нет username)"
    stats_text += (
        f"• {data['full_name']} {uname} — расчетов: {data['calcs']}\n"
    )

  await message.answer(stats_text)


@router.message()
async def handle_message(message: types.Message, bot: Bot):
  user_id = message.from_user.id
  user_name = message.from_user.full_name
  user_username = message.from_user.username

  # Проверяем подписку на канал
  if not await check_subscription(bot, user_id):
    await message.answer(
        "🔒 Для использования бота необходимо подписаться на наш канал @club_reefland.",
        reply_markup=check_sub_keyboard(),
    )
    return

  text = message.text.strip()
  # Поиск трех чисел для расчета (например, 100х50х50 или 100 50 50)
  numbers = re.findall(r"\d+(?:[.,]\d+)?", text)

  if len(numbers) == 3:
    # Логика калькулятора стекла
    length, width, height = map(float, [n.replace(",", ".") for n in numbers])
    volume = (length * width * height) / 1000

    # Простая формула расчета толщины (упрощенный пример)
    rec_glass = max(6.0, (height * 0.5) / 10 + 2)

    # Учет статистики
    if user_id not in user_stats:
      user_stats[user_id] = {
          "full_name": user_name,
          "username": user_username,
          "calcs": 0,
      }
    user_stats[user_id]["calcs"] += 1

    response = (
        f"💧 Объем: ~{int(volume)} л\n\n"
        f"📊 Расчетные данные:\n"
        f"• Рекомендуемое стекло: {round(rec_glass, 1)} мм (Optiwhite или М1)\n"
        f"• Запас прочности: k = ~3.8\n"
        f"• Нагрузка и вес:\n"
        f"• Сухой вес стекла: ~{int(volume * 0.15)} кг\n"
        f"• Вес с водой: ~{int(volume + volume * 0.15)} кг\n\n"
        f"📐 Расчет выполнен для бескаркасных открытых аквариумов."
    )
    await message.answer(
        response, reply_markup=get_result_keyboard(length, width, height, rec_glass)
    )
  else:
    # Если это не размеры, отправляем запрос в Gemini ИИ-справочнику
    await bot.send_chat_action(message.chat.id, "typing")
    try:
      response = ai_client.models.generate_content(
          model="gemini-2.5-flash",
          contents=text,
          config=genai_types.GenerateContentConfig(
              system_instruction=SYSTEM_PROMPT, temperature=0.7
          ),
      )
      await message.answer(response.text)
    except Exception as e:
      logging.error(f"Ошибка Gemini API: {e}")
      await message.answer(
          "Извините, произошла ошибка при обращении к ИИ-ассистенту. Попробуйте сформулировать вопрос иначе."
      )


async def main():
  bot = Bot(token=TELEGRAM_BOT_TOKEN)
  dp = Dispatcher()
  dp.include_router(router)
  await bot.delete_webhook(drop_pending_updates=True)
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
