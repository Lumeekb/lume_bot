import os
import logging
import openai
import requests
from datetime import datetime, timedelta
from flask import Flask, request
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.webhook import get_new_configured_app
from dotenv import load_dotenv

# Загрузка переменных из .env
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))
YCLIENTS_COMPANY_ID = os.getenv("YCLIENTS_COMPANY_ID")
YCLIENTS_API_TOKEN = os.getenv("YCLIENTS_API_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # пример: https://lume-bot.onrender.com/webhook
PORT = int(os.getenv("PORT", 5000))

# Логирование
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

user_states = {}

HEADERS = {
    'Authorization': f'Bearer {YCLIENTS_API_TOKEN}',
    'Content-Type': 'application/json'
}

def get_services():
    url = f"https://api.yclients.com/api/v1/companies/{YCLIENTS_COMPANY_ID}/services"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 200:
        return resp.json().get('data', [])
    else:
        logging.error(f"Ошибка получения услуг YCLIENTS: {resp.status_code} {resp.text}")
        return []

def get_available_slots(service_id, date_str):
    url = f"https://api.yclients.com/api/v1/records/{YCLIENTS_COMPANY_ID}/available_times"
    params = {"service_ids": [service_id], "date": date_str}
    resp = requests.post(url, headers=HEADERS, json=params)
    if resp.status_code == 200:
        return resp.json().get('data', [])
    else:
        logging.error(f"Ошибка получения свободных окон YCLIENTS: {resp.status_code} {resp.text}")
        return []

@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    user_states[message.chat.id] = {'step': 'choose_service'}
    services = get_services()
    if not services:
        await message.answer("Извините, не удалось загрузить услуги, попробуйте позже.")
        return

    user_states[message.chat.id]['services'] = services
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for svc in services:
        keyboard.add(svc['name'])
    await message.answer("Привет! Выберите услугу:", reply_markup=keyboard)

@dp.message_handler()
async def main_handler(message: types.Message):
    chat_id = message.chat.id
    text = message.text.strip()
    state = user_states.get(chat_id, {})

    if state.get('step') == 'choose_service':
        services = state.get('services', [])
        selected_service = next((s for s in services if s['name'] == text), None)
        if not selected_service:
            await message.answer("Пожалуйста, выберите услугу из списка.")
            return
        user_states[chat_id]['selected_service'] = selected_service
        user_states[chat_id]['step'] = 'choose_date'

        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for i in range(6):
            day = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
            keyboard.add(day)
        await message.answer(f"Вы выбрали услугу: {selected_service['name']}\nВыберите дату записи:", reply_markup=keyboard)
        return

    if state.get('step') == 'choose_date':
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            await message.answer("Пожалуйста, выберите дату из предложенных вариантов.")
            return

        user_states[chat_id]['selected_date'] = text
        user_states[chat_id]['step'] = 'choose_time'

        service_id = user_states[chat_id]['selected_service']['id']
        slots = get_available_slots(service_id, text)
        if not slots:
            await message.answer("Извините, на выбранную дату нет свободных окон. Попробуйте другую дату.")
            return

        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for slot in slots:
            keyboard.add(slot['start'])
        await message.answer("Выберите удобное время:", reply_markup=keyboard)
        return

    if state.get('step') == 'choose_time':
        user_states[chat_id]['selected_time'] = text
        user_states[chat_id]['step'] = 'get_name'
        await message.answer("Как вас зовут?")
        return

    if state.get('step') == 'get_name':
        user_states[chat_id]['name'] = text
        user_states[chat_id]['step'] = 'get_phone'
        await message.answer("Укажите ваш номер телефона:")
        return

    if state.get('step') == 'get_phone':
        user_states[chat_id]['phone'] = text

        data = user_states[chat_id]
        msg = f"📅 Новая запись:\n\n💡 Услуга: {data['selected_service']['name']}\n🗓 Дата: {data['selected_date']}\n🕒 Время: {data['selected_time']}\n👤 Имя: {data['name']}\n📱 Телефон: {data['phone']}"

        await bot.send_message(chat_id, "Спасибо! Мы свяжемся с вами для подтверждения записи. ✨")
        await bot.send_message(ADMIN_CHAT_ID, msg)

        user_states.pop(chat_id, None)

# Flask + Webhook
app = Flask(__name__)

@app.route('/')
def index():
    return 'Bot is running!'

@app.route('/webhook', methods=['POST'])
def webhook():
    return get_new_configured_app(dispatcher=dp)(request)

if __name__ == '__main__':
    import asyncio
    async def on_startup(dp):
        await bot.set_webhook(WEBHOOK_URL)
        logging.info("Webhook установлен")

    from aiogram import executor
    executor.set_webhook(dp, webhook_path='/webhook', on_startup=on_startup, skip_updates=True, host="0.0.0.0", port=PORT)
    app.run(host='0.0.0.0', port=PORT)
