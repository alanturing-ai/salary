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
BOT_TOKEN = "7909538433:AAG8ot_W96YoUX_OXTy9QDOzV21Lg-1iqzI"  
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

def get_admin_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("➕ Добавить рейс"))
    keyboard.add(types.KeyboardButton("🗂️ История рейсов"))
    keyboard.add(types.KeyboardButton("🚛 Управление"))
    keyboard.add(types.KeyboardButton("👥 Управление пользователями"))
    return keyboard

# Проверка роли пользователя
async def check_user_access(cursor, user_id, required_role=2):
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    if not result:
        return False
    
    return result[0] <= required_role

# Обработчик команды /start
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    conn = init_db()
    cursor = conn.cursor()
    
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Проверяем наличие пользователя
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        # Новый пользователь - не регистрируем, отправляем шуточное сообщение
        await message.answer("О нет, кажется вы вотермелон, сбросьте 50 кг, чтобы пользоваться ботом!")
    else:
        # Существующий пользователь
        if user[0] == 0:
            await message.answer("Привет! Вы вошли как администратор.", reply_markup=get_admin_keyboard())
        elif user[0] == 1:
            await message.answer("Привет! Вы вошли как редактор.", reply_markup=get_editor_keyboard())
        else:
            await message.answer("Привет! Вы вошли как просмотрщик.", reply_markup=get_viewer_keyboard())
    
    conn.close()

@dp.message_handler(commands=['myid'])
async def cmd_myid(message: types.Message):
    await message.answer(f"Ваш ID: {message.from_user.id}")

@dp.message_handler(commands=['makeadmin'])
async def cmd_makeadmin(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    await message.answer("Ваша роль обновлена до администратора!")
    conn.close()
