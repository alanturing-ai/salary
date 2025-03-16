import logging
from aiogram import executor
from aiogram.utils.exceptions import TelegramAPIError

# Импортируем нашего бота из модуля bot
from bot import dp, bot, init_db

# Импортируем все обработчики
import admin
import drivers
import vehicles
import trips

# Настраиваем логирование (подробнее для отладки)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Обработчик запуска бота
async def on_startup(dispatcher):
    # Инициализируем базу данных
    conn = init_db()
    conn.close()
    
    # Уведомляем о запуске (в консоль)
    logging.info('Бот запущен!')

# Обработчик остановки бота
async def on_shutdown(dispatcher):
    logging.warning('Бот остановлен!')

    # Закрываем соединения с базой данных
    await dispatcher.storage.close()
    await dispatcher.storage.wait_closed()

if __name__ == '__main__':
    try:
        # Запускаем бота
        executor.start_polling(
            dp, 
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            skip_updates=True
        )
    except (KeyboardInterrupt, SystemExit):
        logging.warning('Бот остановлен!')
    except TelegramAPIError as e:
        logging.error(f'Ошибка API Telegram: {e}')
    except Exception as e:
        logging.error(f'Непредвиденная ошибка: {e}')
