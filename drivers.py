from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from bot import dp, bot, check_user_access
import sqlite3

# Состояния для добавления/редактирования водителя
class DriverStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_km_rate = State()
    waiting_for_side_loading_rate = State()
    waiting_for_roof_loading_rate = State()
    waiting_for_regular_downtime_rate = State()
    waiting_for_forced_downtime_rate = State()
    waiting_for_notes = State()
    waiting_for_confirmation = State()

# Клавиатура управления водителями
def get_drivers_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("👤 Добавить водителя"))
    keyboard.add(types.KeyboardButton("📋 Список водителей"))
    keyboard.add(types.KeyboardButton("◀️ Назад"))
    return keyboard

# Обработчик команды для раздела водителей
@dp.message_handler(lambda message: message.text == "🚛 Управление")
async def manage_menu(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("👤 Водители"))
    keyboard.add(types.KeyboardButton("🚚 Автопоезда"))
    keyboard.add(types.KeyboardButton("◀️ Назад"))
    await message.answer("Выберите раздел для управления:", reply_markup=keyboard)

@dp.message_handler(lambda message: message.text == "👤 Водители")
async def manage_drivers(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=1):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    await message.answer("Управление водителями", reply_markup=get_drivers_keyboard())
    conn.close()

# Обработчик для добавления водителя
@dp.message_handler(lambda message: message.text == "👤 Добавить водителя")
async def add_driver(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=1):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    await message.answer("Введите имя водителя:")
    await DriverStates.waiting_for_name.set()
    
    conn.close()

# Последовательность шагов для ввода данных о водителе
@dp.message_handler(state=DriverStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите ставку за километр (в рублях):")
    await DriverStates.waiting_for_km_rate.set()

@dp.message_handler(state=DriverStates.waiting_for_km_rate)
async def process_km_rate(message: types.Message, state: FSMContext):
    try:
        km_rate = float(message.text.replace(',', '.'))
        await state.update_data(km_rate=km_rate)
        await message.answer("Введите ставку за погрузку/разгрузку бокового тента (в рублях):")
        await DriverStates.waiting_for_side_loading_rate.set()
    except ValueError:
        await message.answer("Ошибка! Введите число. Пример: 25.5")

# Обработчик для кнопки "Назад"
@dp.message_handler(lambda message: message.text == "◀️ Назад")
async def back_to_main(message: types.Message):
    from bot import get_editor_keyboard, get_viewer_keyboard
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if await check_user_access(cursor, message.from_user.id, required_role=1):
        await message.answer("Главное меню:", reply_markup=get_editor_keyboard())
    else:
        await message.answer("Главное меню:", reply_markup=get_viewer_keyboard())
    
    conn.close()

# Добавьте недостающие обработчики для полей водителя
@dp.message_handler(state=DriverStates.waiting_for_side_loading_rate)
async def process_side_loading_rate(message: types.Message, state: FSMContext):
    try:
        side_loading_rate = float(message.text.replace(',', '.'))
        await state.update_data(side_loading_rate=side_loading_rate)
        await message.answer("Введите ставку за погрузку/разгрузку крыши (в рублях):")
        await DriverStates.waiting_for_roof_loading_rate.set()
    except ValueError:
        await message.answer("Ошибка! Введите число. Пример: 25.5")

@dp.message_handler(state=DriverStates.waiting_for_roof_loading_rate)
async def process_roof_loading_rate(message: types.Message, state: FSMContext):
    try:
        roof_loading_rate = float(message.text.replace(',', '.'))
        await state.update_data(roof_loading_rate=roof_loading_rate)
        await message.answer("Введите ставку за обычный простой (в рублях/час):")
        await DriverStates.waiting_for_regular_downtime_rate.set()
    except ValueError:
        await message.answer("Ошибка! Введите число. Пример: 25.5")

@dp.message_handler(state=DriverStates.waiting_for_regular_downtime_rate)
async def process_regular_downtime_rate(message: types.Message, state: FSMContext):
    try:
        regular_downtime_rate = float(message.text.replace(',', '.'))
        await state.update_data(regular_downtime_rate=regular_downtime_rate)
        await message.answer("Введите ставку за вынужденный простой (в рублях/час):")
        await DriverStates.waiting_for_forced_downtime_rate.set()
    except ValueError:
        await message.answer("Ошибка! Введите число. Пример: 25.5")

@dp.message_handler(state=DriverStates.waiting_for_forced_downtime_rate)
async def process_forced_downtime_rate(message: types.Message, state: FSMContext):
    try:
        forced_downtime_rate = float(message.text.replace(',', '.'))
        await state.update_data(forced_downtime_rate=forced_downtime_rate)
        await message.answer("Введите примечания (или отправьте '-' если примечаний нет):")
        await DriverStates.waiting_for_notes.set()
    except ValueError:
        await message.answer("Ошибка! Введите число. Пример: 25.5")

@dp.message_handler(state=DriverStates.waiting_for_notes)
async def process_notes(message: types.Message, state: FSMContext):
    notes = message.text
    if notes == "-":
        notes = ""
    
    await state.update_data(notes=notes)
    
    # Получаем данные для отображения
    data = await state.get_data()
    
    # Формируем сообщение с введенными данными
    confirmation_text = (
        f"📌 Данные водителя:\n"
        f"👤 Имя: {data['name']}\n"
        f"💰 Ставка за км: {data['km_rate']} руб\n"
        f"🚚 Боковой тент: {data['side_loading_rate']} руб\n"
        f"🚚 Крыша: {data['roof_loading_rate']} руб\n"
        f"⏱️ Обычный простой: {data['regular_downtime_rate']} руб/час\n"
        f"⏱️ Вынужденный простой: {data['forced_downtime_rate']} руб/час\n"
    )
    
    if notes:
        confirmation_text += f"📝 Примечания: {notes}\n"
    
    confirmation_text += "\nСохранить? (да/нет)"
    
    await message.answer(confirmation_text)
    await DriverStates.waiting_for_confirmation.set()

# Обработчик для списка водителей
@dp.message_handler(lambda message: message.text == "📋 Список водителей")
async def list_drivers(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=1):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    cursor.execute("SELECT id, name, km_rate FROM drivers ORDER BY name")
    drivers = cursor.fetchall()
    
    if not drivers:
        await message.answer("Список водителей пуст. Добавьте водителей с помощью кнопки '👤 Добавить водителя'.", 
                           reply_markup=get_drivers_keyboard())
        conn.close()
        return
    
    # Формируем список водителей
    text = "📋 Список водителей:\n\n"
    
    for driver_id, name, km_rate in drivers:
        text += f"ID: {driver_id} | 👤 {name} | 💰 {km_rate} руб/км\n"
    
    await message.answer(text, reply_markup=get_drivers_keyboard())
    conn.close()

# Финальный обработчик для сохранения водителя
@dp.message_handler(state=DriverStates.waiting_for_confirmation)
async def process_confirmation(message: types.Message, state: FSMContext):
    if message.text.lower() not in ["да", "сохранить", "+"]:
        await message.answer("Отменено. Данные не сохранены.", reply_markup=get_drivers_keyboard())
        await state.finish()
        return
    
    # Получаем все введенные данные
    data = await state.get_data()
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Сохраняем в базу
    cursor.execute(
        """
        INSERT INTO drivers 
        (name, km_rate, side_loading_rate, roof_loading_rate, 
        regular_downtime_rate, forced_downtime_rate, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get('name'),
            data.get('km_rate'),
            data.get('side_loading_rate'),
            data.get('roof_loading_rate'),
            data.get('regular_downtime_rate'),
            data.get('forced_downtime_rate'),
            data.get('notes', '')
        )
    )
    
    # Логируем действие
    cursor.execute(
        "INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)",
        (message.from_user.id, "Добавление водителя", f"Добавлен водитель: {data.get('name')}")
    )
    
    conn.commit()
    conn.close()
    
    await message.answer(
        f"Водитель {data.get('name')} успешно добавлен!", 
        reply_markup=get_drivers_keyboard()
    )
    await state.finish()
