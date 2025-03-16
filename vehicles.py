from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from bot import dp, bot, check_user_access
import sqlite3

# Состояния для добавления/редактирования автопоезда
class VehicleStates(StatesGroup):
    waiting_for_truck_number = State()
    waiting_for_trailer_number = State()
    waiting_for_notes = State()
    waiting_for_confirmation = State()
    waiting_for_vehicle_id = State()
    waiting_for_delete_confirmation = State()

# Клавиатура управления автопоездами
def get_vehicles_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("➕ Добавить автопоезд"))
    keyboard.add(types.KeyboardButton("📋 Список автопоездов"))
    keyboard.add(types.KeyboardButton("◀️ Назад"))
    return keyboard

# Обработчик выбора раздела автопоездов
@dp.message_handler(lambda message: message.text == "🚚 Автопоезда")
async def manage_vehicles(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=1):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    await message.answer("Управление автопоездами", reply_markup=get_vehicles_keyboard())
    conn.close()

# Обработчик для добавления автопоезда
@dp.message_handler(lambda message: message.text == "➕ Добавить автопоезд")
async def add_vehicle(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=1):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    await message.answer("Введите номер тягача:")
    await VehicleStates.waiting_for_truck_number.set()
    
    conn.close()

# Последовательность шагов для ввода данных об автопоезде
@dp.message_handler(state=VehicleStates.waiting_for_truck_number)
async def process_truck_number(message: types.Message, state: FSMContext):
    await state.update_data(truck_number=message.text)
    await message.answer("Введите номер прицепа:")
    await VehicleStates.waiting_for_trailer_number.set()

@dp.message_handler(state=VehicleStates.waiting_for_trailer_number)
async def process_trailer_number(message: types.Message, state: FSMContext):
    await state.update_data(trailer_number=message.text)
    await message.answer("Введите примечания (или отправьте '-' если примечаний нет):")
    await VehicleStates.waiting_for_notes.set()

@dp.message_handler(state=VehicleStates.waiting_for_notes)
async def process_notes(message: types.Message, state: FSMContext):
    notes = message.text
    if notes == "-":
        notes = ""
    
    await state.update_data(notes=notes)
    
    # Получаем данные для отображения
    data = await state.get_data()
    
    # Формируем сообщение с введенными данными
    confirmation_text = (
        f"📌 Данные автопоезда:\n"
        f"🚛 Тягач: {data['truck_number']}\n"
        f"🚜 Прицеп: {data['trailer_number']}\n"
    )
    
    if notes:
        confirmation_text += f"📝 Примечания: {notes}\n"
    
    confirmation_text += "\nСохранить? (да/нет)"
    
    await message.answer(confirmation_text)
    await VehicleStates.waiting_for_confirmation.set()

@dp.message_handler(state=VehicleStates.waiting_for_confirmation)
async def process_confirmation(message: types.Message, state: FSMContext):
    if message.text.lower() not in ["да", "сохранить", "+"]:
        await message.answer("Отменено. Данные не сохранены.", reply_markup=get_vehicles_keyboard())
        await state.finish()
        return
    
    # Получаем все введенные данные
    data = await state.get_data()
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Сохраняем в базу
    cursor.execute(
        """
        INSERT INTO vehicles 
        (truck_number, trailer_number, notes)
        VALUES (?, ?, ?)
        """,
        (
            data.get('truck_number'),
            data.get('trailer_number'),
            data.get('notes', '')
        )
    )
    
    # Логируем действие
    cursor.execute(
        "INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)",
        (message.from_user.id, "Добавление автопоезда", 
         f"Добавлен автопоезд: {data.get('truck_number')}/{data.get('trailer_number')}")
    )
    
    conn.commit()
    conn.close()
    
    await message.answer(
        f"Автопоезд {data.get('truck_number')}/{data.get('trailer_number')} успешно добавлен!", 
        reply_markup=get_vehicles_keyboard()
    )
    await state.finish()

# Обработчик для просмотра списка автопоездов
@dp.message_handler(lambda message: message.text == "📋 Список автопоездов")
async def list_vehicles(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=1):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    cursor.execute("SELECT id, truck_number, trailer_number, notes FROM vehicles ORDER BY id")
    vehicles = cursor.fetchall()
    
    if not vehicles:
        await message.answer("Список автопоездов пуст.", reply_markup=get_vehicles_keyboard())
        conn.close()
        return
    
    # Формируем список автопоездов с кнопками для редактирования/удаления
    text = "📋 Список автопоездов:\n\n"
    
    for vehicle_id, truck, trailer, notes in vehicles:
        text += f"ID: {vehicle_id} | 🚛 {truck} | 🚜 {trailer}"
        if notes:
            text += f" | 📝 {notes}"
        text += "\n"
    
    await message.answer(text, reply_markup=get_vehicles_keyboard())
    conn.close()
