from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot import dp, bot, check_user_access, get_editor_keyboard, get_viewer_keyboard, get_admin_keyboard
import sqlite3
from datetime import datetime, timedelta
import io
import csv
import logging


# Настройка расширенного логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_debug.log"),
        logging.StreamHandler()
    ]
)

# Подменю для работы с рейсами
def get_trips_menu():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        types.KeyboardButton("➕ Добавить рейс"),
        types.KeyboardButton("✏️ Редактировать рейс")
    )
    keyboard.add(
        types.KeyboardButton("⏱️ Добавить простой"),
        types.KeyboardButton("🗂️ История рейсов")
    )
    keyboard.add(
        types.KeyboardButton("🔍 Найти рейс"),
        types.KeyboardButton("📊 Статистика водителей")
    )
    keyboard.add(types.KeyboardButton("↩️ Назад в главное меню"))
    return keyboard

# Обработчик для кнопки "Рейсы"
@dp.message_handler(lambda message: message.text == "🚚 Рейсы")
async def show_trips_menu(message: types.Message):
    await message.answer("Меню работы с рейсами:", reply_markup=get_trips_menu())

# Обработчик для кнопки "Назад в главное меню"
@dp.message_handler(lambda message: message.text == "↩️ Назад в главное меню")
async def back_to_main_menu(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (message.from_user.id,))
    user_role = cursor.fetchone()
    conn.close()
    
    if user_role and user_role[0] == 0:  # Администратор
        await message.answer("Главное меню:", reply_markup=get_admin_keyboard())
    elif user_role and user_role[0] == 1:  # Редактор
        await message.answer("Главное меню:", reply_markup=get_editor_keyboard())
    else:  # Просмотрщик
        await message.answer("Главное меню:", reply_markup=get_viewer_keyboard())



# Состояния для добавления рейса
class TripStates(StatesGroup):
    waiting_for_driver = State()
    waiting_for_vehicle = State()
    waiting_for_trip_1c_number = State()  # Новое состояние для номера рейса из 1С
    waiting_for_loading_city = State()
    waiting_for_unloading_city = State()
    waiting_for_distance = State()
    waiting_for_side_loading = State()
    waiting_for_roof_loading = State()
    waiting_for_regular_downtime = State()
    waiting_for_forced_downtime = State()
    waiting_for_confirmation = State()

# Состояния для редактирования рейса
class EditTripStates(StatesGroup):
    waiting_for_trip_id = State()
    waiting_for_field = State()
    waiting_for_new_value = State()
    waiting_for_confirmation = State()

# Состояния для добавления простоя к существующему рейсу
class DowntimeStates(StatesGroup):
    waiting_for_trip_id = State()
    waiting_for_downtime_type = State()
    waiting_for_hours = State()
    waiting_for_confirmation = State()

# Функция расчета стоимости рейса
def calculate_trip_payment(driver_data, distance, side_loading, roof_loading, reg_downtime=0, forced_downtime=0):
    # Расчет за километры
    km_payment = distance * driver_data['km_rate']
    
    # Расчет за погрузку/разгрузку
    side_loading_payment = side_loading * driver_data['side_loading_rate']
    roof_loading_payment = roof_loading * driver_data['roof_loading_rate']
    
    # Расчет за простои
    regular_downtime_payment = reg_downtime * driver_data['regular_downtime_rate']
    forced_downtime_payment = forced_downtime * driver_data['forced_downtime_rate']
    
    # Общая сумма
    total = km_payment + side_loading_payment + roof_loading_payment + regular_downtime_payment + forced_downtime_payment
    
    return {
        'km_payment': km_payment,
        'side_loading_payment': side_loading_payment,
        'roof_loading_payment': roof_loading_payment,
        'regular_downtime_payment': regular_downtime_payment,
        'forced_downtime_payment': forced_downtime_payment,
        'total': total
    }

# Функция для создания навигационных кнопок (Назад/Отмена)
def get_navigation_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⬅️ Назад", callback_data="trip_back"),
        InlineKeyboardButton("❌ Отмена", callback_data="trip_cancel")
    )
    return keyboard

# Обработчик для добавления рейса
@dp.message_handler(lambda message: message.text == "➕ Добавить рейс")
async def add_trip(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=1):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    # Проверяем наличие водителей и автопоездов
    cursor.execute("SELECT COUNT(*) FROM drivers")
    drivers_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM vehicles")
    vehicles_count = cursor.fetchone()[0]
    
    if drivers_count == 0 or vehicles_count == 0:
        missing = []
        if drivers_count == 0:
            missing.append("водители")
        if vehicles_count == 0:
            missing.append("автопоезда")
        
        await message.answer(f"Невозможно создать рейс. Отсутствуют: {', '.join(missing)}.")
        conn.close()
        return
    
    # Создаем клавиатуру с водителями и навигационными кнопками
    cursor.execute("SELECT id, name FROM drivers ORDER BY name")
    drivers = cursor.fetchall()
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for driver_id, name in drivers:
        keyboard.add(InlineKeyboardButton(f"{name}", callback_data=f"driver_{driver_id}"))
    
    # Добавляем только кнопку отмены, т.к. это первый шаг
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="trip_cancel"))
    
    await message.answer("Выберите водителя:", reply_markup=keyboard)
    await TripStates.waiting_for_driver.set()
    
    conn.close()

# Обработчик для кнопок навигации
@dp.callback_query_handler(lambda c: c.data in ["trip_back", "trip_cancel"], state="*")
async def process_navigation(callback_query: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    
    # Проверяем роль пользователя и показываем соответствующую клавиатуру
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (callback_query.from_user.id,))
    user_role = cursor.fetchone()
    
    if callback_query.data == "trip_cancel":
        # Отмена и возврат в главное меню
        await state.finish()
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="Действие отменено. Возврат в главное меню.",
            reply_markup=None
        )
        
        # Определяем, какую клавиатуру показать
        if user_role and user_role[0] == 0:  # Администратор
            await bot.send_message(
                callback_query.message.chat.id,
                "Главное меню:",
                reply_markup=get_admin_keyboard()
            )
        elif user_role and user_role[0] == 1:  # Редактор
            await bot.send_message(
                callback_query.message.chat.id,
                "Главное меню:",
                reply_markup=get_editor_keyboard()
            )
        else:  # Просмотрщик
            await bot.send_message(
                callback_query.message.chat.id,
                "Главное меню:", 
                reply_markup=get_viewer_keyboard()
            )
        
        conn.close()
        return
    
    elif callback_query.data == "trip_back":
        # Возврат на предыдущий шаг
        if current_state == "TripStates:waiting_for_vehicle":
            # Возврат к выбору водителя
            conn = sqlite3.connect('salary_bot.db')
            cursor = conn.cursor()
            
            cursor.execute("SELECT id, name FROM drivers ORDER BY name")
            drivers = cursor.fetchall()
            
            keyboard = InlineKeyboardMarkup(row_width=1)
            for driver_id, name in drivers:
                keyboard.add(InlineKeyboardButton(f"{name}", callback_data=f"driver_{driver_id}"))
            
            keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="trip_cancel"))
            
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text="Выберите водителя:",
                reply_markup=keyboard
            )
            
            await TripStates.waiting_for_driver.set()
            conn.close()
            
        elif current_state == "TripStates:waiting_for_trip_1c_number":
            # Возврат к выбору автопоезда
            conn = sqlite3.connect('salary_bot.db')
            cursor = conn.cursor()
            
            data = await state.get_data()
            
            cursor.execute("SELECT id, truck_number, trailer_number FROM vehicles ORDER BY truck_number")
            vehicles = cursor.fetchall()
            
            keyboard = InlineKeyboardMarkup(row_width=1)
            for vehicle_id, truck, trailer in vehicles:
                keyboard.add(InlineKeyboardButton(f"{truck} / {trailer}", callback_data=f"vehicle_{vehicle_id}"))
            
            keyboard.add(
                InlineKeyboardButton("⬅️ Назад", callback_data="trip_back"),
                InlineKeyboardButton("❌ Отмена", callback_data="trip_cancel")
            )
            
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=f"Выбран водитель: {data.get('driver_name', '')}\nВыберите автопоезд:",
                reply_markup=keyboard
            )
            
            await TripStates.waiting_for_vehicle.set()
            conn.close()
            
        elif current_state == "TripStates:waiting_for_loading_city":
            # Возврат к вводу номера рейса из 1С
            data = await state.get_data()
            
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=f"Выбран автопоезд: {data.get('truck_number', '')} / {data.get('trailer_number', '')}\nВведите номер рейса из 1С:",
                reply_markup=get_navigation_keyboard()
            )
            
            await TripStates.waiting_for_trip_1c_number.set()
            
        elif current_state == "TripStates:waiting_for_unloading_city":
            # Возврат к вводу города погрузки
            data = await state.get_data()
            
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=f"Номер рейса из 1С: {data.get('trip_1c_number', '')}\nВведите город погрузки:",
                reply_markup=get_navigation_keyboard()
            )
            
            await TripStates.waiting_for_loading_city.set()
            
        elif current_state == "TripStates:waiting_for_distance":
            # Возврат к вводу города разгрузки
            data = await state.get_data()
            
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=f"Город погрузки: {data.get('loading_city', '')}\nВведите город разгрузки:",
                reply_markup=get_navigation_keyboard()
            )
            
            await TripStates.waiting_for_unloading_city.set()
            
        elif current_state == "TripStates:waiting_for_side_loading":
            # Возврат к вводу расстояния
            data = await state.get_data()
            
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=f"Город разгрузки: {data.get('unloading_city', '')}\nВведите расстояние в километрах (только число):",
                reply_markup=get_navigation_keyboard()
            )
            
            await TripStates.waiting_for_distance.set()
            
        elif current_state == "TripStates:waiting_for_roof_loading":
            # Возврат к вводу боковых загрузок
            data = await state.get_data()
            
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=f"Расстояние: {data.get('distance', '')} км\nВведите количество боковых загрузок (число от 0):",
                reply_markup=get_navigation_keyboard()
            )
            
            await TripStates.waiting_for_side_loading.set()
            
        elif current_state == "TripStates:waiting_for_regular_downtime":
            # Возврат к вводу загрузок через крышу
            data = await state.get_data()
            
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=f"Боковых загрузок: {data.get('side_loading', '')}\nВведите количество загрузок через крышу (число от 0):",
                reply_markup=get_navigation_keyboard()
            )
            
            await TripStates.waiting_for_roof_loading.set()
            
        elif current_state == "TripStates:waiting_for_forced_downtime":
            # Возврат к вводу регулярного простоя
            data = await state.get_data()
            
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=f"Загрузок через крышу: {data.get('roof_loading', '')}\nВведите часы регулярного простоя (число от 0):",
                reply_markup=get_navigation_keyboard()
            )
            
            await TripStates.waiting_for_regular_downtime.set()
            
        elif current_state == "TripStates:waiting_for_confirmation":
            # Возврат к вводу вынужденного простоя
            data = await state.get_data()
            
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=f"Регулярный простой: {data.get('regular_downtime', '')} ч\nВведите часы вынужденного простоя (число от 0):",
                reply_markup=get_navigation_keyboard()
            )
            
            await TripStates.waiting_for_forced_downtime.set()
    
    conn.close()
        
# Обработчик выбора водителя
@dp.callback_query_handler(lambda c: c.data.startswith('driver_'), state=TripStates.waiting_for_driver)
async def process_driver_selection(callback_query: types.CallbackQuery, state: FSMContext):
    logging.info(f"Обработка выбора водителя: {callback_query.data}")
    driver_id = int(callback_query.data.split('_')[1])
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Получаем данные о водителе
    cursor.execute(
        """
        SELECT name, km_rate, side_loading_rate, roof_loading_rate, 
               regular_downtime_rate, forced_downtime_rate
        FROM drivers WHERE id = ?
        """, 
        (driver_id,)
    )
    driver_data = cursor.fetchone()
    
    await state.update_data(
        driver_id=driver_id,
        driver_name=driver_data[0],
        km_rate=driver_data[1],
        side_loading_rate=driver_data[2],
        roof_loading_rate=driver_data[3],
        regular_downtime_rate=driver_data[4],
        forced_downtime_rate=driver_data[5]
    )
    
    # Создаем клавиатуру с автопоездами и навигационными кнопками
    cursor.execute("SELECT id, truck_number, trailer_number FROM vehicles ORDER BY truck_number")
    vehicles = cursor.fetchall()
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for vehicle_id, truck, trailer in vehicles:
        keyboard.add(InlineKeyboardButton(f"{truck} / {trailer}", callback_data=f"vehicle_{vehicle_id}"))
    
    # Добавляем навигационные кнопки
    keyboard.add(
        InlineKeyboardButton("⬅️ Назад", callback_data="trip_back"),
        InlineKeyboardButton("❌ Отмена", callback_data="trip_cancel")
    )
    
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text=f"Выбран водитель: {driver_data[0]}\nВыберите автопоезд:",
        reply_markup=keyboard
    )
    
    await TripStates.waiting_for_vehicle.set()
    conn.close()

# Обработчик выбора автопоезда
@dp.callback_query_handler(lambda c: c.data.startswith('vehicle_'), state=TripStates.waiting_for_vehicle)
async def process_vehicle_selection(callback_query: types.CallbackQuery, state: FSMContext):
    vehicle_id = int(callback_query.data.split('_')[1])
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Получаем данные об автопоезде
    cursor.execute("SELECT truck_number, trailer_number FROM vehicles WHERE id = ?", (vehicle_id,))
    truck_number, trailer_number = cursor.fetchone()
    conn.close()
    
    await state.update_data(
        vehicle_id=vehicle_id,
        truck_number=truck_number,
        trailer_number=trailer_number
    )
    
    # Отправляем сообщение с запросом номера рейса из 1С и навигационными кнопками
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text=f"Выбран автопоезд: {truck_number} / {trailer_number}\nВведите номер рейса из 1С:",
        reply_markup=get_navigation_keyboard()
    )
    
    await TripStates.waiting_for_trip_1c_number.set()

# Обработчик ввода номера рейса из 1С
@dp.message_handler(state=TripStates.waiting_for_trip_1c_number)
async def process_trip_1c_number(message: types.Message, state: FSMContext):
    trip_1c_number = message.text.strip()
    
    await state.update_data(trip_1c_number=trip_1c_number)
    
        # Отправляем новое сообщение с кнопками навигации
    keyboard = get_navigation_keyboard()
    sent_message = await message.answer(f"Номер рейса из 1С: {trip_1c_number}\nВведите город погрузки:", reply_markup=keyboard)
    
    await TripStates.waiting_for_loading_city.set()

# Обработчик ввода города погрузки
@dp.message_handler(state=TripStates.waiting_for_loading_city)
async def process_loading_city(message: types.Message, state: FSMContext):
    loading_city = message.text.strip()
    
    if not loading_city:
        await message.answer("Пожалуйста, введите корректное название города погрузки.")
        return
    
    await state.update_data(loading_city=loading_city)
    
    # Отправляем новое сообщение с кнопками навигации
    keyboard = get_navigation_keyboard()
    await message.answer(f"Город погрузки: {loading_city}\nВведите город разгрузки:", reply_markup=keyboard)
    
    await TripStates.waiting_for_unloading_city.set()

# Обработчик ввода города разгрузки
@dp.message_handler(state=TripStates.waiting_for_unloading_city)
async def process_unloading_city(message: types.Message, state: FSMContext):
    unloading_city = message.text.strip()
    
    if not unloading_city:
        await message.answer("Пожалуйста, введите корректное название города разгрузки.")
        return
    
    await state.update_data(unloading_city=unloading_city)
        
    # Отправляем новое сообщение с кнопками навигации
    keyboard = get_navigation_keyboard()
    await message.answer(f"Город разгрузки: {unloading_city}\nВведите расстояние в километрах (только число):", reply_markup=keyboard)
    
    await TripStates.waiting_for_distance.set()

# Обработчик ввода расстояния
@dp.message_handler(state=TripStates.waiting_for_distance)
async def process_distance(message: types.Message, state: FSMContext):
    logging.info(f"Получено значение расстояния: {message.text}")
    try:
        distance = float(message.text.replace(',', '.').strip())
        
        if distance <= 0:
            await message.answer("Расстояние должно быть положительным числом. Введите расстояние снова.")
            return
        
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число. Введите расстояние снова.")
        return
    
    await state.update_data(distance=distance)
    
    # Отправляем новое сообщение с кнопками навигации
    keyboard = get_navigation_keyboard()
    await message.answer(f"Расстояние: {distance} км\nВведите количество боковых загрузок (число от 0):", reply_markup=keyboard)
    
    await TripStates.waiting_for_side_loading.set()

# Обработчик ввода боковых загрузок
@dp.message_handler(state=TripStates.waiting_for_side_loading)
async def process_side_loading(message: types.Message, state: FSMContext):
    try:
        side_loading = int(message.text.strip())
        
        if side_loading < 0:
            await message.answer("Количество боковых загрузок не может быть отрицательным. Введите число снова.")
            return
        
    except ValueError:
        await message.answer("Пожалуйста, введите корректное целое число. Введите количество боковых загрузок снова.")
        return
    
    await state.update_data(side_loading=side_loading)
    
    # Отправляем новое сообщение с кнопками навигации
    keyboard = get_navigation_keyboard()
    await message.answer(f"Боковых загрузок: {side_loading}\nВведите количество загрузок через крышу (число от 0):", reply_markup=keyboard)
    
    await TripStates.waiting_for_roof_loading.set()

# Обработчик ввода загрузок через крышу
@dp.message_handler(state=TripStates.waiting_for_roof_loading)
async def process_roof_loading(message: types.Message, state: FSMContext):
    try:
        roof_loading = int(message.text.strip())
        
        if roof_loading < 0:
            await message.answer("Количество загрузок через крышу не может быть отрицательным. Введите число снова.")
            return
        
    except ValueError:
        await message.answer("Пожалуйста, введите корректное целое число. Введите количество загрузок через крышу снова.")
        return
    
    await state.update_data(roof_loading=roof_loading)
    
    # Отправляем новое сообщение с кнопками навигации
    keyboard = get_navigation_keyboard()
    await message.answer(f"Загрузок через крышу: {roof_loading}\nВведите часы регулярного простоя (число от 0):", reply_markup=keyboard)
    
    await TripStates.waiting_for_regular_downtime.set()

# Обработчик ввода регулярного простоя
@dp.message_handler(state=TripStates.waiting_for_regular_downtime)
async def process_regular_downtime(message: types.Message, state: FSMContext):
    try:
        regular_downtime = float(message.text.replace(',', '.').strip())
        
        if regular_downtime < 0:
            await message.answer("Часы простоя не могут быть отрицательными. Введите число снова.")
            return
        
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число. Введите часы регулярного простоя снова.")
        return
    
    await state.update_data(regular_downtime=regular_downtime)
    
    # Отправляем новое сообщение с кнопками навигации
    keyboard = get_navigation_keyboard()
    await message.answer(f"Регулярный простой: {regular_downtime} ч\nВведите часы вынужденного простоя (число от 0):", reply_markup=keyboard)
    
    await TripStates.waiting_for_forced_downtime.set()

# Обработчик ввода вынужденного простоя
@dp.message_handler(state=TripStates.waiting_for_forced_downtime)
async def process_forced_downtime(message: types.Message, state: FSMContext):
    try:
        forced_downtime = float(message.text.replace(',', '.').strip())
        
        if forced_downtime < 0:
            await message.answer("Часы простоя не могут быть отрицательными. Введите число снова.")
            return
        
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число. Введите часы вынужденного простоя снова.")
        return
    
    # Получаем все данные из состояния
    data = await state.get_data()
    forced_downtime = float(forced_downtime)
    
    # Подготавливаем данные водителя для расчета
    driver_data = {
        'km_rate': data['km_rate'],
        'side_loading_rate': data['side_loading_rate'],
        'roof_loading_rate': data['roof_loading_rate'],
        'regular_downtime_rate': data['regular_downtime_rate'],
        'forced_downtime_rate': data['forced_downtime_rate']
    }
    
    # Рассчитываем оплату
    payment_data = calculate_trip_payment(
        driver_data=driver_data,
        distance=data['distance'],
        side_loading=data['side_loading'],
        roof_loading=data['roof_loading'],
        reg_downtime=data['regular_downtime'],
        forced_downtime=forced_downtime
    )
    
    # Сохраняем данные о вынужденном простое и расчетах
    await state.update_data(
        forced_downtime=forced_downtime,
        km_payment=payment_data['km_payment'],
        side_loading_payment=payment_data['side_loading_payment'],
        roof_loading_payment=payment_data['roof_loading_payment'],
        regular_downtime_payment=payment_data['regular_downtime_payment'],
        forced_downtime_payment=payment_data['forced_downtime_payment'],
        total_payment=payment_data['total']
    )
    
    # Формируем сообщение с итоговой информацией
    data = await state.get_data()  # Обновляем данные после добавления платежной информации
    summary = (
        f"📋 Информация о рейсе:\n\n"
        f"👤 Водитель: {data['driver_name']}\n"
        f"🚛 Автопоезд: {data['truck_number']} / {data['trailer_number']}\n"
        f"📝 Номер рейса из 1С: {data.get('trip_1c_number', 'Не указан')}\n"
        f"🏙️ Маршрут: {data['loading_city']} → {data['unloading_city']}\n"
        f"📏 Расстояние: {data['distance']} км (={payment_data['km_payment']} руб.)\n"
        f"🔄 Загрузки: {data['side_loading']} бок. (={payment_data['side_loading_payment']} руб.), "
        f"{data['roof_loading']} крыша (={payment_data['roof_loading_payment']} руб.)\n"
        f"⏱️ Простои: {data['regular_downtime']} ч рег. (={payment_data['regular_downtime_payment']} руб.), "
        f"{forced_downtime} ч вын. (={payment_data['forced_downtime_payment']} руб.)\n\n"
        f"💰 Итого: {payment_data['total']} руб.\n\n"
        f"Данные верны? Введите 'Да' для сохранения или любой другой текст для отмены."
    )
    
    # Отправляем с кнопками навигации
    keyboard = get_navigation_keyboard()
    await message.answer(summary, reply_markup=keyboard)
    await TripStates.waiting_for_confirmation.set()
    
# Финальный обработчик для подтверждения и сохранения рейса
@dp.message_handler(state=TripStates.waiting_for_confirmation)
async def confirm_trip(message: types.Message, state: FSMContext):
    if message.text.lower() not in ["да", "сохранить", "+"]:
        await message.answer("Отменено. Данные не сохранены.", reply_markup=get_trips_menu())
        await state.finish()
        return
    
    # Получаем все введенные данные
    data = await state.get_data()
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Проверяем, существует ли уже колонка trip_1c_number в таблице trips
        cursor.execute("PRAGMA table_info(trips)")
        columns = cursor.fetchall()
        columns_names = [column[1] for column in columns]
        
        # Если колонки нет, добавляем ее
        if 'trip_1c_number' not in columns_names:
            cursor.execute("ALTER TABLE trips ADD COLUMN trip_1c_number TEXT")
        
        # Сохраняем рейс с номером из 1С
        cursor.execute(
            """
            INSERT INTO trips 
            (driver_id, vehicle_id, loading_city, unloading_city, distance,
             side_loading_count, roof_loading_count, total_payment, trip_1c_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get('driver_id'),
                data.get('vehicle_id'),
                data.get('loading_city'),
                data.get('unloading_city'),
                data.get('distance'),
                data.get('side_loading', 0),
                data.get('roof_loading', 0),
                data.get('total_payment'),
                data.get('trip_1c_number', '')
            )
        )
        trip_id = cursor.lastrowid
        
        # Если есть простои, добавляем их
        if data.get('regular_downtime', 0) > 0:
            reg_payment = data.get('regular_downtime', 0) * data.get('regular_downtime_rate', 0)
            cursor.execute(
                """
                INSERT INTO downtimes (trip_id, type, hours, payment)
                VALUES (?, 1, ?, ?)
                """,
                (trip_id, data.get('regular_downtime'), reg_payment)
            )
        
        if data.get('forced_downtime', 0) > 0:
            forced_payment = data.get('forced_downtime', 0) * data.get('forced_downtime_rate', 0)
            cursor.execute(
                """
                INSERT INTO downtimes (trip_id, type, hours, payment)
                VALUES (?, 2, ?, ?)
                """,
                (trip_id, data.get('forced_downtime'), forced_payment)
            )
        
        # Логируем действие
        cursor.execute(
            "INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)",
            (
                message.from_user.id, 
                "Добавление рейса", 
                f"Рейс #{trip_id}: {data.get('loading_city')} - {data.get('unloading_city')}, {data.get('distance')} км"
            )
        )
        
        conn.commit()
        
        await message.answer(
            f"✅ Рейс успешно сохранен!\n"
            f"№ рейса: {trip_id}\n"
            f"Номер из 1С: {data.get('trip_1c_number', 'Не указан')}\n"
            f"Итоговая сумма: {data.get('total_payment')} руб.",
            reply_markup=get_trips_menu()  # Заменяем на меню рейсов
        )
    
    except Exception as e:
        conn.rollback()
        await message.answer(
            f"❌ Ошибка при сохранении рейса: {str(e)}",
            reply_markup=get_trips_menu()  # Заменяем на меню рейсов
        )
    
    finally:
        conn.close()
        await state.finish()
        
# Обработчик для редактирования рейса
@dp.message_handler(lambda message: message.text == "✏️ Редактировать рейс")
async def edit_trip(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=1):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    # Проверяем наличие рейсов
    cursor.execute("SELECT COUNT(*) FROM trips")
    trips_count = cursor.fetchone()[0]
    
    if trips_count == 0:
        await message.answer("В базе данных нет рейсов для редактирования.")
        conn.close()
        return
    
    # Добавляем клавиатуру с кнопкой отмены
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("↩️ Назад в меню рейсов", callback_data="cancel_edit"))
    
    await message.answer(
        "Введите ID рейса для редактирования:",
        reply_markup=keyboard
    )
    
    await EditTripStates.waiting_for_trip_id.set()
    conn.close()

# Обработчик для кнопки отмены редактирования
@dp.callback_query_handler(lambda c: c.data == "cancel_edit", state=EditTripStates.waiting_for_trip_id)
async def cancel_edit(callback_query: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Редактирование отменено.",
        reply_markup=None
    )
    await bot.send_message(
        callback_query.message.chat.id,
        "Меню работы с рейсами:",
        reply_markup=get_trips_menu()
    )

# Обработчик ввода ID рейса для редактирования
@dp.message_handler(state=EditTripStates.waiting_for_trip_id)
async def process_edit_trip_id(message: types.Message, state: FSMContext):
    try:
        trip_id = int(message.text.strip())
    except ValueError:
        await message.answer("Пожалуйста, введите корректный ID рейса (целое число).")
        return
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Проверяем существование рейса и получаем его данные
    cursor.execute("""
    SELECT t.id, d.name, v.truck_number, v.trailer_number, 
           t.trip_1c_number, t.loading_city, t.unloading_city, 
           t.distance, t.side_loading_count, t.roof_loading_count,
           t.total_payment
    FROM trips t
    JOIN drivers d ON t.driver_id = d.id
    JOIN vehicles v ON t.vehicle_id = v.id
    WHERE t.id = ?
    """, (trip_id,))
    
    trip_data = cursor.fetchone()
    
    if not trip_data:
        await message.answer("Рейс с таким ID не найден. Проверьте номер и попробуйте снова.")
        conn.close()
        return
    
    # Сохраняем ID рейса в состоянии
    await state.update_data(
        trip_id=trip_id
    )
    
    # Создаем текст с информацией о рейсе
    trip_info = (
        f"📋 Информация о рейсе #{trip_data[0]}:\n\n"
        f"👤 Водитель: {trip_data[1]}\n"
        f"🚛 Автопоезд: {trip_data[2]} / {trip_data[3]}\n"
        f"📝 Номер рейса из 1С: {trip_data[4] or 'Не указан'}\n"
        f"🏙️ Погрузка: {trip_data[5]}\n"
        f"🏙️ Разгрузка: {trip_data[6]}\n"
        f"📏 Расстояние: {trip_data[7]} км\n"
        f"🔄 Боковые загрузки: {trip_data[8]}\n"
        f"🔄 Загрузки через крышу: {trip_data[9]}\n"
        f"💰 Итого: {trip_data[10]} руб.\n\n"
        f"Выберите, что редактировать:"
    )
    
    # Создаем клавиатуру с полями для редактирования
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("Номер рейса из 1С", callback_data="edit_trip_1c_number"),
        InlineKeyboardButton("Город погрузки", callback_data="edit_loading_city"),
        InlineKeyboardButton("Город разгрузки", callback_data="edit_unloading_city"),
        InlineKeyboardButton("Расстояние", callback_data="edit_distance"),
        InlineKeyboardButton("Боковые загрузки", callback_data="edit_side_loading"),
        InlineKeyboardButton("Загрузки через крышу", callback_data="edit_roof_loading"),
        InlineKeyboardButton("❌ Отмена", callback_data="trip_cancel")
    )
    
    await message.answer(trip_info, reply_markup=keyboard)
    await EditTripStates.waiting_for_field.set()
    conn.close()

# Обработчик выбора поля для редактирования
@dp.callback_query_handler(lambda c: c.data.startswith('edit_'), state=EditTripStates.waiting_for_field)
async def process_edit_field_selection(callback_query: types.CallbackQuery, state: FSMContext):
    field = callback_query.data.replace('edit_', '')
    
    # Сохраняем выбранное поле в состоянии
    await state.update_data(field=field)
    
    # Определяем текст сообщения в зависимости от выбранного поля
    field_names = {
        'trip_1c_number': 'номер рейса из 1С',
        'loading_city': 'город погрузки',
        'unloading_city': 'город разгрузки',
        'distance': 'расстояние (км)',
        'side_loading': 'количество боковых загрузок',
        'roof_loading': 'количество загрузок через крышу'
    }
    
    message_text = f"Введите новое значение для поля '{field_names.get(field, field)}':"
    
    if field in ['distance', 'side_loading', 'roof_loading']:
        message_text += "\n(введите только число)"
    
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text=message_text,
        reply_markup=get_navigation_keyboard()
    )
    
    await EditTripStates.waiting_for_new_value.set()

# Обработчик ввода нового значения для поля
@dp.message_handler(state=EditTripStates.waiting_for_new_value)
async def process_edit_new_value(message: types.Message, state: FSMContext):
    # Получаем данные из состояния
    data = await state.get_data()
    field = data.get('field')
    new_value = message.text.strip()
    
    # Валидация введенного значения в зависимости от поля
    if field == 'distance':
        try:
            new_value = float(new_value.replace(',', '.'))
            if new_value <= 0:
                await message.answer("Расстояние должно быть положительным числом. Введите значение снова.")
                return
        except ValueError:
            await message.answer("Пожалуйста, введите корректное число. Введите значение снова.")
            return
    
    elif field in ['side_loading', 'roof_loading']:
        try:
            new_value = int(new_value)
            if new_value < 0:
                await message.answer("Количество загрузок не может быть отрицательным. Введите значение снова.")
                return
        except ValueError:
            await message.answer("Пожалуйста, введите корректное целое число. Введите значение снова.")
            return
    
    # Сохраняем новое значение в состоянии
    await state.update_data(new_value=new_value)
    
    # Получаем информацию о рейсе для подтверждения
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT t.id, d.name, t.loading_city, t.unloading_city, t.trip_1c_number
    FROM trips t
    JOIN drivers d ON t.driver_id = d.id
    WHERE t.id = ?
    """, (data['trip_id'],))
    
    trip_info = cursor.fetchone()
    conn.close()
    
    # Определяем названия полей для отображения
    field_names = {
        'trip_1c_number': 'Номер рейса из 1С',
        'loading_city': 'Город погрузки',
        'unloading_city': 'Город разгрузки',
        'distance': 'Расстояние (км)',
        'side_loading': 'Количество боковых загрузок',
        'roof_loading': 'Количество загрузок через крышу'
    }
    
    # Формируем сообщение для подтверждения
    confirmation_text = (
        f"📋 Редактирование рейса #{trip_info[0]}\n\n"
        f"👤 Водитель: {trip_info[1]}\n"
        f"🗺️ Маршрут: {trip_info[2]} → {trip_info[3]}\n"
        f"📝 Номер рейса из 1С: {trip_info[4] or 'Не указан'}\n\n"
        f"Вы хотите изменить поле '{field_names.get(field, field)}' на значение '{new_value}'.\n\n"
        f"Подтвердите изменение: введите 'Да' для сохранения или любой другой текст для отмены."
    )
    
    # Отправляем с кнопками навигации
    keyboard = get_navigation_keyboard()
    await message.answer(confirmation_text, reply_markup=keyboard)
    
    await EditTripStates.waiting_for_confirmation.set()

# Обработчик подтверждения редактирования
@dp.message_handler(state=EditTripStates.waiting_for_confirmation)
async def confirm_edit_trip(message: types.Message, state: FSMContext):
    if message.text.lower() not in ["да", "сохранить", "+"]:
        await message.answer("Отменено. Данные не изменены.", reply_markup=get_trips_menu())
        await state.finish()
        return
    
    # Получаем все данные из состояния
    data = await state.get_data()
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Если редактируем расстояние, нужно пересчитать стоимость рейса
        if data['field'] in ['distance', 'side_loading', 'roof_loading']:
            # Получаем текущие данные рейса
            cursor.execute("""
            SELECT driver_id, distance, side_loading_count, roof_loading_count
            FROM trips
            WHERE id = ?
            """, (data['trip_id'],))
            
            trip_data = cursor.fetchone()
            
            # Получаем ставки водителя
            cursor.execute("""
            SELECT km_rate, side_loading_rate, roof_loading_rate
            FROM drivers
            WHERE id = ?
            """, (trip_data[0],))
            
            rates = cursor.fetchone()
            
            # Текущая оплата за километры
            current_km_payment = trip_data[1] * rates[0]
            current_side_loading_payment = trip_data[2] * rates[1]
            current_roof_loading_payment = trip_data[3] * rates[2]
            
            # Новые значения
            new_distance = data['new_value'] if data['field'] == 'distance' else trip_data[1]
            new_side_loading = data['new_value'] if data['field'] == 'side_loading' else trip_data[2]
            new_roof_loading = data['new_value'] if data['field'] == 'roof_loading' else trip_data[3]
            
            # Новая оплата
            new_km_payment = new_distance * rates[0]
            new_side_loading_payment = new_side_loading * rates[1]
            new_roof_loading_payment = new_roof_loading * rates[2]
            
            # Разница в оплате
            payment_difference = (
                (new_km_payment - current_km_payment) +
                (new_side_loading_payment - current_side_loading_payment) +
                (new_roof_loading_payment - current_roof_loading_payment)
            )
            
            # Обновляем поле и общую сумму оплаты
            field_db_name = {
                'distance': 'distance',
                'side_loading': 'side_loading_count',
                'roof_loading': 'roof_loading_count'
            }.get(data['field'])
            
            cursor.execute(f"""
            UPDATE trips
            SET {field_db_name} = ?, total_payment = total_payment + ?
            WHERE id = ?
            """, (data['new_value'], payment_difference, data['trip_id']))
        
        else:
            # Для текстовых полей просто обновляем значение
            field_db_name = {
                'trip_1c_number': 'trip_1c_number',
                'loading_city': 'loading_city',
                'unloading_city': 'unloading_city'
            }.get(data['field'])
            
            cursor.execute(f"""
            UPDATE trips
            SET {field_db_name} = ?
            WHERE id = ?
            """, (data['new_value'], data['trip_id']))
        
        # Логируем действие
        cursor.execute(
            "INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)",
            (
                message.from_user.id, 
                "Редактирование рейса", 
                f"Рейс #{data['trip_id']}: изменено поле '{data['field']}' на '{data['new_value']}'"
            )
        )
        
        conn.commit()
        
        await message.answer(
            f"✅ Рейс успешно отредактирован!\n"
            f"Рейс #{data['trip_id']}\n"
            f"Поле: {data['field']}\n"
            f"Новое значение: {data['new_value']}",
            reply_markup=get_trips_menu()  # Заменяем на меню рейсов
        )
    
    except Exception as e:
        conn.rollback()
        await message.answer(
            f"❌ Ошибка при редактировании рейса: {str(e)}",
            reply_markup=get_trips_menu()  # Заменяем на меню рейсов
        )
    
    finally:
        conn.close()
        await state.finish()
        
# Функция для обновления схемы базы данных (добавление колонки trip_1c_number)
async def update_database_schema():
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Проверяем, существует ли уже колонка trip_1c_number в таблице trips
        cursor.execute("PRAGMA table_info(trips)")
        columns = cursor.fetchall()
        columns_names = [column[1] for column in columns]
        
        # Если колонки нет, добавляем ее
        if 'trip_1c_number' not in columns_names:
            cursor.execute("ALTER TABLE trips ADD COLUMN trip_1c_number TEXT")
            conn.commit()
            logging.info("Добавлена колонка trip_1c_number в таблицу trips")
    except Exception as e:
        logging.error(f"Ошибка при обновлении схемы базы данных: {str(e)}")
    finally:
        conn.close()

# Обработчик на старте бота для обновления базы данных
@dp.message_handler(commands=['start'])
async def on_start(message: types.Message):
    # Обновляем схему базы данных
    await update_database_schema()
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Проверяем, зарегистрирован ли пользователь
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (message.from_user.id,))
    user_role = cursor.fetchone()
    
    if user_role:
        # Пользователь уже зарегистрирован, отправляем клавиатуру в зависимости от роли
        if user_role[0] == 1:  # Редактор
            await message.answer(f"Привет! Вы вошли как администратор.", reply_markup=get_editor_keyboard())
        else:  # Просмотрщик
            await message.answer(f"Привет! Вы вошли как пользователь.", reply_markup=get_viewer_keyboard())
    else:
        # Пользователь не зарегистрирован, показываем сообщение
        await message.answer("Вы не зарегистрированы в системе. Обратитесь к администратору.")
    
    conn.close()

# Обработчик для просмотра истории рейсов
@dp.message_handler(lambda message: message.text == "🗂️ История рейсов")
async def view_trips_history(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=2):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    # Создаем клавиатуру для выбора периода
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("За последние 7 дней", callback_data="history_7days"),
        InlineKeyboardButton("За последние 30 дней", callback_data="history_30days"),
        InlineKeyboardButton("За все время", callback_data="history_all"),
        InlineKeyboardButton("Экспорт в CSV", callback_data="history_export"),
        InlineKeyboardButton("Назад", callback_data="trip_cancel")
    )
    
    await message.answer("Выберите период для просмотра:", reply_markup=keyboard)
    conn.close()

# Обработчик выбора периода истории
@dp.callback_query_handler(lambda c: c.data.startswith('history_'))
async def process_history_selection(callback_query: types.CallbackQuery):
    period = callback_query.data.split('_')[1]
    
    # Если выбран экспорт, вызываем функцию экспорта
    if period == "export":
        await export_history(callback_query)
        return
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    query = """
    SELECT t.id, d.name, v.truck_number, v.trailer_number,
           t.loading_city, t.unloading_city, t.distance,
           t.total_payment, t.created_at, t.trip_1c_number
    FROM trips t
    JOIN drivers d ON t.driver_id = d.id
    JOIN vehicles v ON t.vehicle_id = v.id
    """
    
    params = tuple()
    
    if period == "7days":
        query += " WHERE t.created_at >= datetime('now', '-7 days')"
    elif period == "30days":
        query += " WHERE t.created_at >= datetime('now', '-30 days')"
    
    query += " ORDER BY t.created_at DESC LIMIT 10"
    
    cursor.execute(query, params)
    trips = cursor.fetchall()
    
    if not trips:
        await bot.answer_callback_query(callback_query.id)
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="За выбранный период рейсов не найдено."
        )
        conn.close()
        return

    # Обработчик для кнопки "Назад" в истории рейсов
@dp.callback_query_handler(lambda c: c.data == "trip_cancel" and c.message.text and "Выберите период для просмотра" in c.message.text)
async def history_back_to_menu(callback_query: types.CallbackQuery):
    # Специальная обработка для возврата из истории рейсов в главное меню
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Возврат в главное меню.",
        reply_markup=None
    )
    
    # Определяем роль пользователя
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (callback_query.from_user.id,))
    user_role = cursor.fetchone()
    conn.close()
    
    # Проверяем роль и показываем соответствующую клавиатуру
    if user_role and user_role[0] == 0:  # Если роль = 0 (Администратор)
        await bot.send_message(
            callback_query.message.chat.id,
            "Главное меню:",
            reply_markup=get_admin_keyboard()  # Используем клавиатуру администратора
        )
    elif user_role and user_role[0] == 1:  # Если роль = 1 (Редактор)
        await bot.send_message(
            callback_query.message.chat.id,
            "Главное меню:",
            reply_markup=get_editor_keyboard()  # Используем клавиатуру редактора
        )
    else:  # В остальных случаях (Просмотрщик)
        await bot.send_message(
            callback_query.message.chat.id,
            "Главное меню:",
            reply_markup=get_viewer_keyboard()  # Используем клавиатуру просмотрщика
        )
    
    # Формируем сообщение с историей
    text = f"📋 История рейсов {get_period_name(period)}:\n\n"
    
    for trip in trips:
        trip_id, driver, truck, trailer, load_city, unload_city, distance, payment, date, trip_1c_number = trip
        text += (
            f"🔹 Рейс #{trip_id} ({date.split(' ')[0]})\n"
            f"👤 Водитель: {driver}\n"
            f"🚛 ТС: {truck}/{trailer}\n"
            f"📝 Номер из 1С: {trip_1c_number or 'Не указан'}\n"
            f"🗺️ Маршрут: {load_city} → {unload_city} ({distance} км)\n"
            f"💰 Оплата: {payment} руб.\n\n"
        )
    
    # Ограничиваем длину сообщения, если оно слишком большое
    if len(text) > 4096:
        text = text[:4000] + "...\n\n(Показаны не все рейсы из-за ограничения длины сообщения)"
    
    await bot.answer_callback_query(callback_query.id)
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text=text
    )
    
    conn.close()

# Вспомогательная функция для названия периода
def get_period_name(period):
    if period == "7days":
        return "за последние 7 дней"
    elif period == "30days":
        return "за последние 30 дней"
    else:
        return "за все время"

# Функция экспорта истории в CSV
async def export_history(callback_query):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Получаем все рейсы
        cursor.execute("""
        SELECT t.id, d.name, v.truck_number, v.trailer_number,
               t.trip_1c_number, t.loading_city, t.unloading_city, t.distance,
               t.side_loading_count, t.roof_loading_count,
               t.total_payment, t.created_at
        FROM trips t
        JOIN drivers d ON t.driver_id = d.id
        JOIN vehicles v ON t.vehicle_id = v.id
        ORDER BY t.created_at DESC
        """)
        
        trips = cursor.fetchall()
        
        if not trips:
            await bot.answer_callback_query(callback_query.id)
            await bot.send_message(
                callback_query.message.chat.id,
                "Нет данных для экспорта."
            )
            return
        
        # Создаем CSV в памяти
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';', quotechar='"')
        
        # Заголовки
        writer.writerow([
            "ID", "Водитель", "Тягач", "Прицеп", "Номер из 1С", "Город погрузки", 
            "Город разгрузки", "Расстояние (км)", "Боковой тент", 
            "Крыша", "Сумма (руб)", "Дата"
        ])
        
        # Данные
        for trip in trips:
            writer.writerow(trip)
        
        # Конвертируем в байты
        csv_bytes = output.getvalue().encode('utf-8-sig')
        
        # Отправляем файл
        filename = f"trips_history_{datetime.now().strftime('%Y-%m-%d')}.csv"
        
        await bot.answer_callback_query(callback_query.id)
        await bot.send_document(
            callback_query.message.chat.id,
            (filename, io.BytesIO(csv_bytes)),
            caption="История рейсов"
        )
    
    except Exception as e:
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.message.chat.id,
            f"Ошибка при экспорте: {str(e)}"
        )
    
    finally:
        conn.close()

# Обновление клавиатуры главного меню с добавлением кнопки редактирования
def get_editor_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        types.KeyboardButton("➕ Добавить рейс"),
        types.KeyboardButton("✏️ Редактировать рейс"),
        types.KeyboardButton("⏱️ Добавить простой"),
        types.KeyboardButton("🗂️ История рейсов"),
        types.KeyboardButton("🔍 Найти рейс"),
        types.KeyboardButton("📊 Статистика водителей"),
        types.KeyboardButton("🚛 Управление")
    )
    return keyboard

# Обработчик для добавления простоя к существующему рейсу
@dp.message_handler(lambda message: message.text == "⏱️ Добавить простой")
async def add_downtime(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=1):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    # Проверяем наличие рейсов
    cursor.execute("SELECT COUNT(*) FROM trips")
    trips_count = cursor.fetchone()[0]
    
    if trips_count == 0:
        await message.answer("Нет рейсов для добавления простоя.")
        conn.close()
        return
    
    # Добавляем клавиатуру с кнопкой отмены
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("↩️ Назад в меню рейсов", callback_data="cancel_downtime"))
    
    await message.answer(
        "Введите ID рейса для добавления простоя:",
        reply_markup=keyboard
    )
    
    await DowntimeStates.waiting_for_trip_id.set()
    conn.close()

# Обработчик для кнопки отмены добавления простоя
@dp.callback_query_handler(lambda c: c.data == "cancel_downtime", state=DowntimeStates.waiting_for_trip_id)
async def cancel_downtime(callback_query: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Добавление простоя отменено.",
        reply_markup=None
    )
    await bot.send_message(
        callback_query.message.chat.id,
        "Меню работы с рейсами:",
        reply_markup=get_trips_menu()
    )
    
# Обработчик ввода ID рейса для простоя
@dp.message_handler(state=DowntimeStates.waiting_for_trip_id)
async def process_trip_id_for_downtime(message: types.Message, state: FSMContext):
    try:
        trip_id = int(message.text.strip())
    except ValueError:
        await message.answer("Пожалуйста, введите корректный ID рейса (целое число).")
        return
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Проверяем существование рейса
    cursor.execute("""
    SELECT t.id, d.name, t.loading_city, t.unloading_city
    FROM trips t
    JOIN drivers d ON t.driver_id = d.id
    WHERE t.id = ?
    """, (trip_id,))
    
    trip_data = cursor.fetchone()
    
    if not trip_data:
        await message.answer("Рейс с таким ID не найден. Проверьте номер и попробуйте снова.")
        conn.close()
        return
    
    await state.update_data(
        trip_id=trip_id,
        trip_info=f"Рейс #{trip_data[0]}: Водитель {trip_data[1]}, {trip_data[2]} → {trip_data[3]}"
    )
    
    # Получаем данные о водителе для расчета оплаты
    cursor.execute("""
    SELECT d.regular_downtime_rate, d.forced_downtime_rate
    FROM trips t
    JOIN drivers d ON t.driver_id = d.id
    WHERE t.id = ?
    """, (trip_id,))
    
    downtime_rates = cursor.fetchone()
    
    await state.update_data(
        regular_downtime_rate=downtime_rates[0],
        forced_downtime_rate=downtime_rates[1]
    )
    
    # Создаем клавиатуру для выбора типа простоя
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("Регулярный простой", callback_data="downtime_regular"),
        InlineKeyboardButton("Вынужденный простой", callback_data="downtime_forced"),
        InlineKeyboardButton("❌ Отмена", callback_data="trip_cancel")
    )
    
    await message.answer(
        f"Выбран {trip_data[0]}\n"
        f"Водитель: {trip_data[1]}\n"
        f"Маршрут: {trip_data[2]} → {trip_data[3]}\n\n"
        f"Выберите тип простоя:",
        reply_markup=keyboard
    )
    
    await DowntimeStates.waiting_for_downtime_type.set()
    conn.close()

# Обработчик выбора типа простоя
@dp.callback_query_handler(lambda c: c.data.startswith('downtime_'), state=DowntimeStates.waiting_for_downtime_type)
async def process_downtime_type(callback_query: types.CallbackQuery, state: FSMContext):
    downtime_type = callback_query.data.split('_')[1]
    
    if downtime_type == "regular":
        await state.update_data(downtime_type=1, downtime_name="Регулярный простой")
    else:
        await state.update_data(downtime_type=2, downtime_name="Вынужденный простой")
    
    data = await state.get_data()
    
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text=f"Выбран {data['trip_info']}\nТип простоя: {data['downtime_name']}\n\nВведите количество часов простоя:",
        reply_markup=get_navigation_keyboard()
    )
    
    await DowntimeStates.waiting_for_hours.set()

# Обработчик ввода часов простоя
@dp.message_handler(state=DowntimeStates.waiting_for_hours)
async def process_downtime_hours(message: types.Message, state: FSMContext):
    try:
        hours = float(message.text.replace(',', '.').strip())
        
        if hours <= 0:
            await message.answer("Количество часов должно быть положительным числом. Введите часы снова.")
            return
        
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число. Введите часы снова.")
        return
    
    # Получаем данные из состояния
    data = await state.get_data()
    
    # Рассчитываем оплату за простой
    rate = data['regular_downtime_rate'] if data['downtime_type'] == 1 else data['forced_downtime_rate']
    payment = hours * rate
    
    await state.update_data(
        hours=hours,
        payment=payment
    )
    
    # Формируем сообщение для подтверждения
    summary = (
        f"📋 Информация о простое:\n\n"
        f"{data['trip_info']}\n"
        f"Тип простоя: {data['downtime_name']}\n"
        f"Количество часов: {hours}\n"
        f"Ставка: {rate} руб/час\n"
        f"Сумма оплаты: {payment} руб\n\n"
        f"Данные верны? Введите 'Да' для сохранения или любой другой текст для отмены."
    )
    
    # Отправляем с кнопками навигации
    keyboard = get_navigation_keyboard()
    await message.answer(summary, reply_markup=keyboard)
    await DowntimeStates.waiting_for_confirmation.set()

# Обработчик подтверждения добавления простоя
@dp.message_handler(state=DowntimeStates.waiting_for_confirmation)
async def confirm_downtime(message: types.Message, state: FSMContext):
    if message.text.lower() not in ["да", "сохранить", "+"]:
        await message.answer("Отменено. Данные не сохранены.", reply_markup=get_trips_menu())
        await state.finish()
        return
    
    # Получаем данные из состояния
    data = await state.get_data()
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Добавляем простой в базу данных
        cursor.execute(
            """
            INSERT INTO downtimes (trip_id, type, hours, payment)
            VALUES (?, ?, ?, ?)
            """,
            (data['trip_id'], data['downtime_type'], data['hours'], data['payment'])
        )
        
        # Обновляем общую сумму рейса
        cursor.execute(
            """
            UPDATE trips
            SET total_payment = total_payment + ?
            WHERE id = ?
            """,
            (data['payment'], data['trip_id'])
        )
        
        # Логируем действие
        cursor.execute(
            "INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)",
            (
                message.from_user.id, 
                "Добавление простоя", 
                f"Рейс #{data['trip_id']}: {data['downtime_name']}, {data['hours']} ч, {data['payment']} руб."
            )
        )
        
        conn.commit()
        
        await message.answer(
            f"✅ Простой успешно добавлен!\n"
            f"Рейс #{data['trip_id']}\n"
            f"Тип: {data['downtime_name']}\n"
            f"Часы: {data['hours']}\n"
            f"Оплата: {data['payment']} руб.",
            reply_markup=get_trips_menu()
        )
    
    except Exception as e:
        conn.rollback()
        await message.answer(
            f"❌ Ошибка при добавлении простоя: {str(e)}",
            reply_markup=get_trips_menu()
        )
    
    finally:
        conn.close()
        await state.finish()
        
# Обработчик для поиска и просмотра конкретного рейса
@dp.message_handler(lambda message: message.text == "🔍 Найти рейс")
async def search_trip(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=2):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    # Проверяем наличие рейсов
    cursor.execute("SELECT COUNT(*) FROM trips")
    trips_count = cursor.fetchone()[0]
    
    if trips_count == 0:
        await message.answer("В базе данных нет рейсов.")
        conn.close()
        return
    
    await message.answer(
        "Введите ID рейса или фамилию водителя для поиска:"
    )
    
    conn.close()

# Обработчик для поиска рейса
@dp.message_handler(lambda message: message.text.startswith("/trip_"))
async def view_trip_by_id(message: types.Message):
    try:
        trip_id = int(message.text.split("_")[1])
    except (ValueError, IndexError):
        await message.answer("Неверный формат ID рейса. Используйте формат /trip_123")
        return
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Получаем информацию о рейсе
    cursor.execute("""
    SELECT t.id, d.name, v.truck_number, v.trailer_number,
           t.loading_city, t.unloading_city, t.distance,
           t.side_loading_count, t.roof_loading_count,
           t.total_payment, t.created_at, t.trip_1c_number
    FROM trips t
    JOIN drivers d ON t.driver_id = d.id
    JOIN vehicles v ON t.vehicle_id = v.id
    WHERE t.id = ?
    """, (trip_id,))
    
    trip = cursor.fetchone()
    
    if not trip:
        await message.answer(f"Рейс с ID {trip_id} не найден.")
        conn.close()
        return
    
    # Получаем информацию о простоях
    cursor.execute("""
    SELECT type, hours, payment
    FROM downtimes
    WHERE trip_id = ?
    ORDER BY type
    """, (trip_id,))
    
    downtimes = cursor.fetchall()
    
    # Формируем текст сообщения
    trip_id, driver, truck, trailer, load_city, unload_city, distance, side_loading, roof_loading, payment, date, trip_1c_number = trip
    
    text = (
        f"📋 Информация о рейсе #{trip_id}\n\n"
        f"📅 Дата: {date.split(' ')[0]}\n"
        f"👤 Водитель: {driver}\n"
        f"🚛 Автопоезд: {truck} / {trailer}\n"
        f"📝 Номер рейса из 1С: {trip_1c_number or 'Не указан'}\n"
        f"🗺️ Маршрут: {load_city} → {unload_city}\n"
        f"📏 Расстояние: {distance} км\n"
        f"🔄 Загрузки: {side_loading} боковых, {roof_loading} через крышу\n"
    )
    
    if downtimes:
        text += "\n⏱️ Простои:\n"
        for dtype, hours, dpayment in downtimes:
            downtime_type = "Регулярный" if dtype == 1 else "Вынужденный"
            text += f"  • {downtime_type}: {hours} ч. ({dpayment} руб.)\n"
    
    text += f"\n💰 Итоговая оплата: {payment} руб."
    
    await message.answer(text)
    conn.close()

# Обработчик поиска по тексту
@dp.message_handler(lambda message: message.text not in ["➕ Добавить рейс", "✏️ Редактировать рейс", "🗂️ История рейсов", "⏱️ Добавить простой", "🔍 Найти рейс", "🚛 Управление", "📊 Статистика водителей"])
async def search_trips(message: types.Message):
    search_text = message.text.strip().lower()
    
    if not search_text:
        return
    
    # Проверяем, является ли ввод числом (ID рейса)
    try:
        trip_id = int(search_text)
        # Если да, делаем поиск по ID
        await view_trip_by_id(types.Message(text=f"/trip_{trip_id}", from_user=message.from_user, chat=message.chat))
        return
    except ValueError:
        pass
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Поиск по имени водителя, городам, номерам ТС и номеру из 1С
    cursor.execute("""
    SELECT t.id, d.name, t.loading_city, t.unloading_city, t.created_at, t.trip_1c_number
    FROM trips t
    JOIN drivers d ON t.driver_id = d.id
    JOIN vehicles v ON t.vehicle_id = v.id
    WHERE 
        LOWER(d.name) LIKE ? OR
        LOWER(t.loading_city) LIKE ? OR
        LOWER(t.unloading_city) LIKE ? OR
        LOWER(v.truck_number) LIKE ? OR
        LOWER(v.trailer_number) LIKE ? OR
        LOWER(t.trip_1c_number) LIKE ?
    ORDER BY t.created_at DESC
    LIMIT 10
    """, (f"%{search_text}%", f"%{search_text}%", f"%{search_text}%", f"%{search_text}%", f"%{search_text}%", f"%{search_text}%"))
    
    trips = cursor.fetchall()
    
    if not trips:
        await message.answer(f"По запросу '{search_text}' ничего не найдено.")
        conn.close()
        return
    
    # Создаем клавиатуру с результатами поиска
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    for trip_id, driver, loading, unloading, date, trip_1c_number in trips:
        date_short = date.split(" ")[0]
        trip_1c_info = f", 1С:{trip_1c_number}" if trip_1c_number else ""
        btn_text = f"#{trip_id}: {driver}, {loading}-{unloading}{trip_1c_info} ({date_short})"
        keyboard.add(InlineKeyboardButton(btn_text, callback_data=f"view_trip_{trip_id}"))
    
    await message.answer(
        f"Найдено {len(trips)} рейсов по запросу '{search_text}'.\nВыберите рейс для просмотра:",
        reply_markup=keyboard
    )
    
    conn.close()

# Обработчик выбора рейса из результатов поиска
@dp.callback_query_handler(lambda c: c.data.startswith('view_trip_'))
async def process_trip_selection(callback_query: types.CallbackQuery):
    trip_id = int(callback_query.data.split('_')[2])
    
    await bot.answer_callback_query(callback_query.id)
    await view_trip_by_id(types.Message(text=f"/trip_{trip_id}", from_user=callback_query.from_user, chat=callback_query.message.chat))

# Обработчик для статистики водителей
@dp.message_handler(lambda message: message.text == "📊 Статистика водителей")
async def driver_statistics(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=1):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    # Получаем статистику по водителям за последние 30 дней
    cursor.execute("""
    SELECT d.name, 
           COUNT(t.id) as trips_count,
           SUM(t.distance) as total_distance,
           SUM(t.total_payment) as total_payment
    FROM drivers d
    LEFT JOIN trips t ON d.id = t.driver_id AND t.created_at >= datetime('now', '-30 days')
    GROUP BY d.id
    ORDER BY total_payment DESC
    """)
    
    stats = cursor.fetchall()
    
    if not stats:
        await message.answer("Нет данных для статистики.")
        conn.close()
        return
    
    text = "📊 Статистика водителей за последние 30 дней:\n\n"
    
    for name, trips_count, total_distance, total_payment in stats:
        if trips_count is None or trips_count == 0:
            text += f"👤 {name}: нет рейсов\n\n"
        else:
            text += (
                f"👤 {name}:\n"
                f"  • Рейсов: {trips_count}\n"
                f"  • Пробег: {int(total_distance) if total_distance else 0} км\n"
                f"  • Заработок: {int(total_payment) if total_payment else 0} руб.\n\n"
            )
    
    await message.answer(text)
    conn.close()

# Универсальный обработчик всех текстовых сообщений
@dp.message_handler(content_types=types.ContentTypes.TEXT, state="*")
async def universal_text_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    logging.info(f"УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК: Сообщение '{message.text}' в состоянии {current_state}")
    
    # Словарь соответствия состояний и функций-обработчиков
    handlers = {
        "TripStates:waiting_for_trip_1c_number": process_trip_1c_number,
        "TripStates:waiting_for_loading_city": process_loading_city,
        "TripStates:waiting_for_unloading_city": process_unloading_city,
        "TripStates:waiting_for_distance": process_distance,
        "TripStates:waiting_for_side_loading": process_side_loading,
        "TripStates:waiting_for_roof_loading": process_roof_loading,
        "TripStates:waiting_for_regular_downtime": process_regular_downtime,
        "TripStates:waiting_for_forced_downtime": process_forced_downtime,
        "TripStates:waiting_for_confirmation": confirm_trip
    }
    
    # Если текущее состояние есть в словаре, вызываем соответствующий обработчик
    if current_state in handlers:
        handler = handlers[current_state]
        try:
            await handler(message, state)
        except Exception as e:
            logging.error(f"Ошибка при обработке сообщения: {e}")
            await message.answer(f"Произошла ошибка при обработке сообщения. Пожалуйста, попробуйте еще раз.")
