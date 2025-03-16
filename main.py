import logging
import sqlite3
from aiogram import Bot, Dispatcher, executor, types

TOKEN = "ВСТАВЬ_СЮДА_СВОЙ_ТОКЕН"  # <-- Не забудь заключить в кавычки!

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# 1) ФУНКЦИЯ ИНИЦИАЛИЗАЦИИ БД
def init_db():
    conn = sqlite3.connect('salary.db')
    c = conn.cursor()
    # Таблица пользователей
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        role TEXT
    )
    ''')
    # Таблица водителей
    c.execute('''
    CREATE TABLE IF NOT EXISTS drivers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        rate_per_km REAL,
        side_load_rate REAL,
        roof_load_rate REAL,
        normal_downtime_rate REAL,
        forced_downtime_rate REAL
    )
    ''')
    # Таблица автопоездов
    c.execute('''
    CREATE TABLE IF NOT EXISTS trains (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tractor_number TEXT,
        trailer_number TEXT,
        notes TEXT
    )
    ''')
    # Таблица рейсов
    c.execute('''
    CREATE TABLE IF NOT EXISTS trips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        driver_id INTEGER,
        train_id INTEGER,
        load_city TEXT,
        unload_city TEXT,
        distance REAL,
        side_load_count INTEGER,
        roof_load_count INTEGER,
        total_cost REAL,
        created_at TEXT,
        FOREIGN KEY(driver_id) REFERENCES drivers(id),
        FOREIGN KEY(train_id) REFERENCES trains(id)
    )
    ''')
    # Таблица простоев
    c.execute('''
    CREATE TABLE IF NOT EXISTS downtime (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trip_id INTEGER,
        downtime_type TEXT,
        hours REAL,
        cost REAL,
        FOREIGN KEY(trip_id) REFERENCES trips(id)
    )
    ''')
    # Таблица логов
    c.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        timestamp TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    ''')
    conn.commit()
    conn.close()

# 2) ОБРАБОТЧИК /start
@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    await message.answer("Привет! Я бот для расчёта зарплаты водителям.")

# 3) ФУНКЦИЯ ПОЛУЧЕНИЯ РОЛИ ПОЛЬЗОВАТЕЛЯ
def get_user_role(telegram_id):
    conn = sqlite3.connect('salary.db')
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE telegram_id = ?", (telegram_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

# 4) /adduser, /deluser — управление пользователями
@dp.message_handler(commands=['adduser'])
async def add_user_command(message: types.Message):
    sender_role = get_user_role(message.from_user.id)
    if sender_role != 'admin':
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    args = message.text.split()
    if len(args) != 3:
        await message.answer("Используйте: /adduser <telegram_id> <role>")
        return

    try:
        new_telegram_id = int(args[1])
        new_role = args[2]
    except ValueError:
        await message.answer("Некорректный telegram_id.")
        return

    conn = sqlite3.connect('salary.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (telegram_id, role) VALUES (?, ?)", (new_telegram_id, new_role))
        conn.commit()
        await message.answer("Пользователь успешно добавлен!")
    except sqlite3.IntegrityError:
        await message.answer("Пользователь с таким telegram_id уже существует.")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
    finally:
        conn.close()

@dp.message_handler(commands=['deluser'])
async def del_user_command(message: types.Message):
    sender_role = get_user_role(message.from_user.id)
    if sender_role != 'admin':
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("Используйте: /deluser <telegram_id>")
        return

    try:
        target_telegram_id = int(args[1])
    except ValueError:
        await message.answer("Некорректный telegram_id.")
        return

    conn = sqlite3.connect('salary.db')
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE telegram_id = ?", (target_telegram_id,))
    conn.commit()
    if c.rowcount:
        await message.answer("Пользователь успешно удалён.")
    else:
        await message.answer("Пользователь не найден.")
    conn.close()

# 5) Проверка роли
def has_access(role):
    return role in ['admin', 'editor']

# 6) /adddriver, /editdriver, /deletedriver, /drivers — управление водителями
@dp.message_handler(commands=['adddriver'])
async def add_driver_command(message: types.Message):
    user_role = get_user_role(message.from_user.id)
    if not has_access(user_role):
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    args = message.text.split()
    if len(args) != 7:
        await message.answer(
            "Использование: /adddriver <Имя> <Ставка_км> <Боковая_погр> <Крыша_погр> <Обычн_простой> <Вынужд_простой>"
        )
        return

    _, name, rate_per_km, side_load_rate, roof_load_rate, normal_downtime_rate, forced_downtime_rate = args

    try:
        conn = sqlite3.connect('salary.db')
        c = conn.cursor()
        c.execute('''
            INSERT INTO drivers (
                name, rate_per_km, side_load_rate, roof_load_rate, normal_downtime_rate, forced_downtime_rate
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            name,
            float(rate_per_km),
            float(side_load_rate),
            float(roof_load_rate),
            float(normal_downtime_rate),
            float(forced_downtime_rate)
        ))
        conn.commit()
        await message.answer(f"Водитель {name} успешно добавлен!")
    except Exception as e:
        await message.answer(f"Ошибка при добавлении: {e}")
    finally:
        conn.close()

@dp.message_handler(commands=['editdriver'])
async def edit_driver_command(message: types.Message):
    user_role = get_user_role(message.from_user.id)
    if not has_access(user_role):
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    args = message.text.split()
    if len(args) != 8:
        await message.answer(
            "Использование: /editdriver <ID> <Имя> <Ставка_км> <Боковая_погр> <Крыша_погр> <Обычн_простой> <Вынужд_простой>"
        )
        return

    _, driver_id, name, rate_per_km, side_load_rate, roof_load_rate, normal_downtime_rate, forced_downtime_rate = args

    try:
        conn = sqlite3.connect('salary.db')
        c = conn.cursor()
        c.execute('''
            UPDATE drivers
            SET name = ?, rate_per_km = ?, side_load_rate = ?, roof_load_rate = ?, 
                normal_downtime_rate = ?, forced_downtime_rate = ?
            WHERE id = ?
        ''', (
            name,
            float(rate_per_km),
            float(side_load_rate),
            float(roof_load_rate),
            float(normal_downtime_rate),
            float(forced_downtime_rate),
            int(driver_id)
        ))
        conn.commit()
        if c.rowcount:
            await message.answer(f"Водитель ID {driver_id} успешно изменён.")
        else:
            await message.answer("Водитель с таким ID не найден.")
    except Exception as e:
        await message.answer(f"Ошибка при редактировании: {e}")
    finally:
        conn.close()

@dp.message_handler(commands=['deletedriver'])
async def delete_driver_command(message: types.Message):
    user_role = get_user_role(message.from_user.id)
    if not has_access(user_role):
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /deletedriver <ID_водителя>")
        return

    _, driver_id = args

    try:
        conn = sqlite3.connect('salary.db')
        c = conn.cursor()
        c.execute("DELETE FROM drivers WHERE id = ?", (driver_id,))
        conn.commit()
        if c.rowcount:
            await message.answer(f"Водитель ID {driver_id} успешно удалён.")
        else:
            await message.answer("Водитель с таким ID не найден.")
    except Exception as e:
        await message.answer(f"Ошибка при удалении: {e}")
    finally:
        conn.close()

@dp.message_handler(commands=['drivers'])
async def list_drivers_command(message: types.Message):
    conn = sqlite3.connect('salary.db')
    c = conn.cursor()
    c.execute("SELECT id, name, rate_per_km, side_load_rate, roof_load_rate, normal_downtime_rate, forced_downtime_rate FROM drivers")
    rows = c.fetchall()
    conn.close()

    if not rows:
        await message.answer("Нет водителей в базе.")
        return

    text_lines = []
    for row in rows:
        driver_id, name, rate_km, side_rate, roof_rate, nd_rate, fd_rate = row
        text_lines.append(
            f"ID: {driver_id}\n"
            f"Имя: {name}\n"
            f"Ставка/км: {rate_km}\n"
            f"Погр (бок): {side_rate}\n"
            f"Погр (крыша): {roof_rate}\n"
            f"Простой обычный: {nd_rate}\n"
            f"Простой вынужденный: {fd_rate}\n"
            "-----------------------"
        )
    await message.answer("\n".join(text_lines))

# 7) СТАРТ ПРИ ЗАПУСКЕ
if __name__ == '__main__':
    init_db()  # создаём таблицы
    executor.start_polling(dp, skip_updates=True)
