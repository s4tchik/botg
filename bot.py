# -*- coding: utf-8 -*-
import logging
import requests
import sqlite3
import time 
from aiogram import Bot, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters import CommandStart
from aiogram.dispatcher.filters import Command

# Настройки
API_TOKEN = ''
HUGGINGFACE_API_TOKEN = ''
DATABASE_FILE = 'db.db'

# Подключение к базе данных SQLite
con = sqlite3.connect(DATABASE_FILE)
cur = con.cursor()

# Создание таблиц в базе данных
cur.execute('''CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    question_num INTEGER DEFAULT 0
)''')
cur.execute('''CREATE TABLE IF NOT EXISTS conversations(
    id INTEGER PRIMARY KEY,
    uid INTEGER,
    question TEXT,
    create_date INT,
    answer TEXT,
    is_show BOOL DEFAULT 1
)''')

# Инициализация бота
logging.basicConfig(format=u'%(filename)s [LINE:%(lineno)d] #%(levelname)-8s [%(asctime)s]  %(message)s', level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# Функция для получения ответа от Hugging Face API
def get_huggingface_response(prompt):
    url = "https://api-inference.huggingface.co/models/gpt2"
    headers = {
        'Authorization': f'Bearer {HUGGINGFACE_API_TOKEN}'
    }
    payload = {
        "inputs": prompt
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        logging.error(f"Ошибка при запросе к Hugging Face API: {response.text}")
        return None
    return response.json()

# Обработчик команды /start
@dp.message_handler(CommandStart())
async def start(message: types.Message):
    user_db = cur.execute("SELECT * FROM users WHERE id = ?", (message.from_user.id,)).fetchone()
    temp = message.from_user.first_name.replace('"', '""')
    
    if user_db is None:
        cur.execute("INSERT INTO users (id, username, first_name) VALUES (?, ?, ?)", 
                    (message.from_user.id, message.from_user.username or "no_username", temp))
    elif user_db[2] != message.from_user.first_name:
        cur.execute("UPDATE users SET first_name = ? WHERE id = ?", (temp, message.from_user.id))
    elif user_db[1] != message.from_user.username:
        cur.execute("UPDATE users SET username = ? WHERE id = ?", (message.from_user.username, message.from_user.id))
    
    con.commit()

    await message.answer(
        '''<b>Привет!</b>

        Этот бот открывает вам доступ к продуктам OpenAI (через Hugging Face API).

        ⚡️Бот использует <b>модель GPT-2 от Hugging Face</b> для генерации ответов.

        <b>Что умеет бот:</b>
        1. <i>Писать и редактировать тексты</i>
        2. <i>Переводить с любого языка на любой</i>
        3. <i>Писать и редактировать код</i>
        4. <i>Отвечать на вопросы</i>

        Вы можете общаться с ботом, задавая вопросы на любом языке.

        ✉️ Чтобы получить <b>текстовый ответ</b>, просто напишите в чат ваш вопрос.

        🔄 Чтобы удалить <b>контекст диалога</b> используйте команду /deletecontext.''', 
        parse_mode=types.ParseMode.HTML
    )

# Обработчик команды /deletecontext
@dp.message_handler(commands=['deletecontext'])
async def deletecontext(message: types.Message):
    cur.execute("UPDATE conversations SET is_show = 0 WHERE uid = ?", (message.from_user.id,))
    con.commit()
    await message.answer('<b>Контекст удален.</b>', parse_mode=types.ParseMode.HTML)

# Основной обработчик текста
@dp.message_handler(content_types=['text'])
async def handle_message(message: types.Message):
    user_db = cur.execute("SELECT * FROM users WHERE id = ?", (message.from_user.id,)).fetchone()
    temp = message.from_user.first_name.replace('"', '""')
    
    if user_db is None:
        cur.execute("INSERT INTO users (id, username, first_name) VALUES (?, ?, ?)", 
                    (message.from_user.id, message.from_user.username or "no_username", temp))
    elif user_db[2] != message.from_user.first_name:
        cur.execute("UPDATE users SET first_name = ? WHERE id = ?", (temp, message.from_user.id))
    elif user_db[1] != message.from_user.username:
        cur.execute("UPDATE users SET username = ? WHERE id = ?", (message.from_user.username, message.from_user.id))
    
    con.commit()

    # Получаем текущие сообщения из базы данных (контекст)
    conversation = cur.execute("SELECT * FROM conversations WHERE uid = ? AND is_show = 1", (message.from_user.id,)).fetchall()
    context = [{'role': 'user', 'content': x[2]} for x in conversation]

    # Отправляем запрос к Hugging Face
    response = get_huggingface_response(message.text)
    
    if response is None:
        await message.answer("Произошла ошибка при получении ответа.")
        return

    # Логируем весь ответ от API для диагностики
    logging.info(f"Ответ от Hugging Face: {response}")

    # Обработка ответа и извлечение текста
    try:
        answer = response[0]['generated_text'] if isinstance(response, list) and len(response) > 0 else "Извините, произошла ошибка."
    except KeyError as e:
        logging.error(f"Ошибка при обработке ответа от Hugging Face: {e}")
        answer = "Извините, произошла ошибка."
    
    # Сохраняем вопрос и ответ в базу данных
    cur.execute("INSERT INTO conversations (uid, question, create_date, answer) VALUES (?, ?, ?, ?)", 
                (message.from_user.id, message.text, int(time.time()), answer))
    con.commit()

    # Отправляем ответ пользователю
    await message.answer(answer)

# Запуск бота
if __name__ == '__main__':
    try:
        executor.start_polling(dp, skip_updates=True)
    except Exception as e:
        logging.error(f"Ошибка при запуске бота: {e}")
