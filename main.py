import os
import logging
import openai
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")  # Your Telegram user ID as string
PORT = int(os.getenv("PORT", 5000))

# Set up logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

# Simple in-memory state
user_states = {}

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    user_states[message.chat.id] = {}
    await message.reply("\u2728 Привет! Я ИИ-помощник салона красоты Lumé. Напиши, что бы ты хотела узнать или на какую услугу записаться.")

@dp.message_handler()
async def handle_message(message: types.Message):
    chat_id = message.chat.id
    text = message.text.strip()

    if 'name' not in user_states.get(chat_id, {}):
        user_states[chat_id]['intent'] = await get_intent_from_openai(text)
        await message.reply("Как вас зовут?")
        return

    if 'phone' not in user_states[chat_id]:
        user_states[chat_id]['name'] = text
        await message.reply("Укажите, пожалуйста, ваш номер телефона.")
        return

    user_states[chat_id]['phone'] = text

    intent = user_states[chat_id]['intent']
    name = user_states[chat_id]['name']
    phone = user_states[chat_id]['phone']

    msg = f"\ud83d\udcc5 Новая заявка:\n\n\ud83d\udd11 Имя: {name}\n\ud83d\udcf1 Телефон: {phone}\n\ud83d\udca1 Запрос: {intent}"
    await bot.send_message(chat_id, "Спасибо! Мы свяжемся с вами для подтверждения записи. \u2728")
    await bot.send_message(int(ADMIN_CHAT_ID), msg)

    user_states.pop(chat_id, None)

async def get_intent_from_openai(text):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Ты помощник салона красоты. Кратко определи, какую услугу хочет клиент."},
                {"role": "user", "content": text}
            ]
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        return "Не удалось определить услугу. Клиент написал: " + text

# Minimal Flask server to keep Render Web Service alive
app = Flask(__name__)

@app.route("/")
def status():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

if __name__ == '__main__':
    threading.Thread(target=run_flask).start()
    executor.start_polling(dp, skip_updates=True)

