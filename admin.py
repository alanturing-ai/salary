from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Command
from bot import dp, bot, check_user_access
import sqlite3

# Состояния для FSM
class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_role = State()
    waiting_for_delete_confirmation = State()

# Клавиатура админа
def get_admin_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("🔑 Назначить роль"))
    keyboard.add(types.KeyboardButton("🗑️ Удалить роль"))
    keyboard.add(types.KeyboardButton("📋 Список пользователей"))
    keyboard.add(types.KeyboardButton("◀️ Назад"))
    return keyboard

# Обработчик команды /admin
@dp.message_handler(Command("admin"))
async def cmd_admin(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if await check_user_access(cursor, message.from_user.id, required_role=0):
        await message.answer("Панель администратора", reply_markup=get_admin_keyboard())
    else:
        await message.answer("У вас нет доступа к этой команде.")
    
    conn.close()

@dp.message_handler(lambda message: message.text == "🔑 Назначить роль")
async def assign_role(message: types.Message, state: FSMContext):
    # Сначала сбрасываем любое активное состояние
    await state.finish()
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=0):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    await message.answer("Введите Telegram ID пользователя:")
    await AdminStates.waiting_for_user_id.set()
    
    conn.close()

# Обработчик ввода ID пользователя
@dp.message_handler(state=AdminStates.waiting_for_user_id)
async def process_user_id(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text)
        await state.update_data(user_id=user_id)
        
        # Клавиатура для выбора роли
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add(types.KeyboardButton("0 - Администратор"))
        keyboard.add(types.KeyboardButton("1 - Редактор"))
        keyboard.add(types.KeyboardButton("2 - Просмотрщик"))
        
        await message.answer("Выберите роль:", reply_markup=keyboard)
        await AdminStates.waiting_for_role.set()
    except ValueError:
        await message.answer("Ошибка! Введите числовой ID.")

# Обработчик выбора роли
@dp.message_handler(state=AdminStates.waiting_for_role)
async def process_role(message: types.Message, state: FSMContext):
    role_text = message.text
    
    if "0" in role_text:
        role = 0
    elif "1" in role_text:
        role = 1
    elif "2" in role_text:
        role = 2
    else:
        await message.answer("Некорректная роль. Выберите из предложенных вариантов.")
        return
    
    user_data = await state.get_data()
    user_id = user_data.get("user_id")
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Проверяем существует ли пользователь
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    # Если пользователь существует, обновляем его роль
    if result:
        cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
        action = "обновлена"
    # Если пользователя нет, создаем нового
    else:
        cursor.execute("INSERT INTO users (user_id, role) VALUES (?, ?)", (user_id, role))
        action = "назначена"
    
    # Логируем действие
    cursor.execute(
        "INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)",
        (message.from_user.id, "Назначение роли", f"Пользователю {user_id} {action} роль {role}")
    )
    
    conn.commit()
    conn.close()
    
    # Показываем сообщение об успехе и сбрасываем состояние
    await message.answer(
        f"✅ Пользователю с ID {user_id} {action} роль: {role}",
        reply_markup=get_admin_keyboard()
    )
    await state.finish()

@dp.message_handler(lambda message: message.text == "👥 Управление пользователями")
async def manage_users(message: types.Message, state: FSMContext):
    # Сначала сбрасываем любое активное состояние
    await state.finish()
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if await check_user_access(cursor, message.from_user.id, required_role=0):
        await message.answer("Панель администратора", reply_markup=get_admin_keyboard())
    else:
        await message.answer("У вас нет доступа к этой команде.")
    
    conn.close()

# Обработчик кнопки "Удалить роль"
@dp.message_handler(lambda message: message.text == "🗑️ Удалить роль")
async def delete_role(message: types.Message, state: FSMContext):
    # Сначала сбрасываем любое активное состояние
    await state.finish()
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=0):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    await message.answer("Введите Telegram ID пользователя:")
    await AdminStates.waiting_for_delete_confirmation.set()
    
    conn.close()

# Обработчик кнопки "Список пользователей"
@dp.message_handler(lambda message: message.text == "📋 Список пользователей")
async def list_users(message: types.Message, state: FSMContext):
    # Сначала сбрасываем любое активное состояние
    await state.finish()
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=0):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    # Код вывода списка пользователей...
    
    conn.close()

# Обработчик кнопки "Назад" в панели администратора
@dp.message_handler(lambda message: message.text == "◀️ Назад", state="*")
async def admin_back(message: types.Message, state: FSMContext):
    # Сбрасываем любое текущее состояние
    await state.finish()
    
    from bot import get_admin_keyboard, get_editor_keyboard, get_viewer_keyboard
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Проверяем роль пользователя
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (message.from_user.id,))
    user_role = cursor.fetchone()
    
    if user_role and user_role[0] == 0:  # Администратор
        await message.answer("Возврат в главное меню.", reply_markup=get_admin_keyboard())
    elif await check_user_access(cursor, message.from_user.id, required_role=1):  # Редактор
        await message.answer("Возврат в главное меню.", reply_markup=get_editor_keyboard())
    else:  # Просмотрщик
        await message.answer("Возврат в главное меню.", reply_markup=get_viewer_keyboard())
    
    conn.close()
