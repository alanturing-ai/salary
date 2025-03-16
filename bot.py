import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import sqlite3
import os
from database import init_db

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
BOT_TOKEN = "YOUR_TOKEN_HERE"  # Замените на свой токен
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

# Клавиатуры для ролей
def get_editor_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("➕ Добавить рейс"))
    keyboard.add(types.KeyboardButton("🗂️ История рейсов"))
    keyboard.add(types.KeyboardButton("🚛 Управление"))
    return keyboard

def get_viewer_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("📊 Актуальные данные"))
    return keyboard

# Проверка роли пользователя
async def check_user_access(cursor, user_id, required_role=2):
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    if not result:
        return False
    
    return result[0] <= required_role

# Обработчик команды /start
@dp.message_handler(comm
