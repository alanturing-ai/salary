import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
import sqlite3
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
BOT_TOKEN = "7909538433:AAG8ot_W96YoUX_OXTy9QDOzV21Lg-1iqzI" 
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Подключение к базе данных
def init_db():
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    # Здесь будут запросы на создание таблиц
    conn.commit()
    return conn

# Обработчик команды /start
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я бот для расчета зарплаты водителям.")

# Запуск бота
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
