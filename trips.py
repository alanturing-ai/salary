from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot import dp, bot, check_user_access, get_editor_keyboard, get_viewer_keyboard
import sqlite3
from datetime import datetime, timedelta
import io
import csv

# Состояния для добавления рейса
class TripStates(StatesGroup):
    waiting_for_driver = State()
    waiting_for_vehicle = State()
    waiting_for_loading_city = State()
    waiting_for_unloading_city = State()
    waiting_for_distance = State()
    waiting_for_side_loading = State()
    waiting_for_roof_loading = State()
    waiting_for_regular_downtime = State()
    waiting_for_forced_downtime = State()
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
    
    # Создаем клавиатуру с водителями
    cursor.execute("SELECT id, name FROM drivers ORDER BY name")
    drivers = cursor.fetchall()
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for driver_id, name in drivers:
        keyboard.add(InlineKeyboardButton(f"{name}", callback_data=f"driver_{driver_id}"))
    
    await message.answer("Выберите водителя:", reply_markup=keyboard)
    await TripStates.waiting_for_driver.set()
    
    conn.close()

# Обработчик выбора водителя
@dp.callback_query_handler(lambda c: c.data.startswith('driver_'), state=TripStates.waiting_for_driver)
async def process_driver_selection(callback_query: types.CallbackQuery, state: FSMContext):
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
    
    # Создаем клавиатуру с автопоездами
    cursor.execute("SELECT id, truck_number, trailer_number FROM vehicles ORDER BY truck_number")
    vehicles = cursor.fetchall()
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for vehicle_id, truck, trailer in vehicles:
        keyboard.add(InlineKeyboardButton(f"{truck} / {trailer}", callback_data=f"vehicle_{vehicle_id}"))
    
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text=f"Выбран водитель: {driver_data[0]}\nВыберите автопоезд:",
        reply_markup=keyboard
    )
    
    await TripStates.waiting_for_vehicle.set()
    conn.close()

# Продолжите добавлять обработчики для остальных состояний рейса
# ...

# Финальный обработчик для подтверждения и сохранения рейса
@dp.message_handler(state=TripStates.waiting_for_confirmation)
async def confirm_trip(message: types.Message, state: FSMContext):
    if message.text.lower() not in ["да", "сохранить", "+"]:
        await message.answer("Отменено. Данные не сохранены.", reply_markup=get_editor_keyboard())
        await state.finish()
        return
    
    # Получаем все введенные данные
    data = await state.get_data()
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Сохраняем рейс
    cursor.execute(
        """
        INSERT INTO trips 
        (driver_id, vehicle_id, loading_city, unloading_city, distance,
         side_loading_count, roof_loading_count, total_payment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get('driver_id'),
            data.get('vehicle_id'),
            data.get('loading_city'),
            data.get('unloading_city'),
            data.get('distance'),
            data.get('side_loading', 0),
            data.get('roof_loading', 0),
            data.get('total_payment')
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
    conn.close()
    
    await message.answer(
        f"Рейс успешно сохранен!\n"
        f"Итоговая сумма: {data.get('total_payment')} руб.",
        reply_markup=get_editor_keyboard()
    )
    await state.finish()

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
        InlineKeyboardButton("Экспорт в CSV", callback_data="history_export")
    )
    
    await message.answer("Выберите период для просмотра:", reply_markup=keyboard)
    conn.close()

# Обработчик выбора периода истории
@dp.callback_query_handler(lambda c: c.data.startswith('history_'))
async def process_history_selection(callback_query: types.CallbackQuery):
    period = callback_query.data.split('_')[1]
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    query = """
    SELECT t.id, d.name, v.truck_number, v.trailer_number,
           t.loading_city, t.unloading_city, t.distance,
           t.total_payment, t.created_at
    FROM trips t
    JOIN drivers d ON t.driver_id = d.id
    JOIN vehicles v ON t.vehicle_id = v.id
    """
    
    params = tuple()
    
    if period == "7days":
        query += " WHERE t.created_at >= datetime('now', '-7 days')"
    elif period == "30days":
        query += " WHERE t.created_at >= datetime('now', '-30 days')"
    elif period == "export":
        # Обработка экспорта - отдельная функция
        await export_history(callback_query)
        return
    
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
    
    # Формируем сообщение с историей
    text = f"📋 История рейсов {get_period_name(period)}:\n\n"
    
    for trip in trips:
        trip_id, driver, truck, trailer, load_city, unload_city, distance, payment, date = trip
        text += (
            f"🔹 Рейс #{trip_id} ({date.split(' ')[0]})\n"
            f"👤 Водитель: {driver}\n"
            f"🚛 ТС: {truck}/{trailer}\n"
            f"🗺️ Маршрут: {load_city} → {unload_city} ({distance} км)\n"
            f"💰 Оплата: {payment} руб.\n\n"
        )
    
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
    
    # Получаем все рейсы
    cursor.execute("""
    SELECT t.id, d.name, v.truck_number, v.trailer_number,
           t.loading_city, t.unloading_city, t.distance,
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
        conn.close()
        return
    
    # Создаем CSV в памяти
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quotechar='"')
    
    # Заголовки
    writer.writerow([
        "ID", "Водитель", "Тягач", "Прицеп", "Город погрузки", 
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
    
    conn.close()
