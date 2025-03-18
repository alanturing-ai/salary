from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from bot import dp, bot, check_user_access
import sqlite3
import aiogram.utils.exceptions

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
    
    await message.answer("Введите ФИО водителя:")
    await DriverStates.waiting_for_name.set()
    
    conn.close()

# Последовательность шагов для ввода данных о водителе
@dp.message_handler(state=DriverStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    # Проверяем, не нажата ли кнопка "Назад"
    if message.text == "◀️ Назад":
        await state.finish()
        await message.answer("Действие отменено", reply_markup=get_drivers_keyboard())
        return
    await state.update_data(name=message.text)
    await message.answer("Введите ставку за километр (в рублях):")
    await DriverStates.waiting_for_km_rate.set()

@dp.message_handler(state=DriverStates.waiting_for_km_rate)
async def process_km_rate(message: types.Message, state: FSMContext):
    # Проверяем, не нажата ли кнопка "Назад"
    if message.text == "◀️ Назад":
        await state.finish()
        await message.answer("Действие отменено", reply_markup=get_drivers_keyboard())
        return
    try:
        km_rate = float(message.text.replace(',', '.'))
        await state.update_data(km_rate=km_rate)
        await message.answer("Введите ставку за погрузку/разгрузку бокового тента (в рублях):")
        await DriverStates.waiting_for_side_loading_rate.set()
    except ValueError:
        await message.answer("Ошибка! Введите число. Пример: 25.5")

# Обработчик для кнопки "Назад"
@dp.message_handler(lambda message: message.text == "◀️ Назад", state="*")
async def back_button_handler(message: types.Message, state: FSMContext):
    # Получаем и сбрасываем текущее состояние
    current_state = await state.get_state()
    if current_state:
        await state.finish()
    
    from bot import get_editor_keyboard, get_viewer_keyboard
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if await check_user_access(cursor, message.from_user.id, required_role=1):
        await message.answer("Действие отменено. Возврат в главное меню.", reply_markup=get_editor_keyboard())
    else:
        await message.answer("Действие отменено. Возврат в главное меню.", reply_markup=get_viewer_keyboard())
    
    conn.close()
    
    # Важно! Сообщаем, что сообщение обработано, чтобы оно не попало в другие обработчики
    return

@dp.message_handler(state=DriverStates.waiting_for_side_loading_rate)
async def process_side_loading_rate(message: types.Message, state: FSMContext):
    # Проверяем, не нажата ли кнопка "Назад"
    if message.text == "◀️ Назад":
        await state.finish()
        await message.answer("Действие отменено", reply_markup=get_drivers_keyboard())
        return
    try:
        side_loading_rate = float(message.text.replace(',', '.'))
        await state.update_data(side_loading_rate=side_loading_rate)
        await message.answer("Введите ставку за погрузку/разгрузку крыши (в рублях):")
        await DriverStates.waiting_for_roof_loading_rate.set()
    except ValueError:
        await message.answer("Ошибка! Введите число. Пример: 25.5")

@dp.message_handler(state=DriverStates.waiting_for_roof_loading_rate)
async def process_roof_loading_rate(message: types.Message, state: FSMContext):
    # Проверяем, не нажата ли кнопка "Назад"
    if message.text == "◀️ Назад":
        await state.finish()
        await message.answer("Действие отменено", reply_markup=get_drivers_keyboard())
        return
    try:
        roof_loading_rate = float(message.text.replace(',', '.'))
        await state.update_data(roof_loading_rate=roof_loading_rate)
        await message.answer("Введите ставку за обычный простой (в рублях/день):")
        await DriverStates.waiting_for_regular_downtime_rate.set()
    except ValueError:
        await message.answer("Ошибка! Введите число. Пример: 25.5")

@dp.message_handler(state=DriverStates.waiting_for_regular_downtime_rate)
async def process_regular_downtime_rate(message: types.Message, state: FSMContext):
    # Проверяем, не нажата ли кнопка "Назад"
    if message.text == "◀️ Назад":
        await state.finish()
        await message.answer("Действие отменено", reply_markup=get_drivers_keyboard())
        return
    try:
        regular_downtime_rate = float(message.text.replace(',', '.'))
        await state.update_data(regular_downtime_rate=regular_downtime_rate)
        await message.answer("Введите ставку за вынужденный простой (в рублях/день):")
        await DriverStates.waiting_for_forced_downtime_rate.set()
    except ValueError:
        await message.answer("Ошибка! Введите число. Пример: 25.5")

@dp.message_handler(state=DriverStates.waiting_for_forced_downtime_rate)
async def process_forced_downtime_rate(message: types.Message, state: FSMContext):
    # Проверяем, не нажата ли кнопка "Назад"
    if message.text == "◀️ Назад":
        await state.finish()
        await message.answer("Действие отменено", reply_markup=get_drivers_keyboard())
        return
    try:
        forced_downtime_rate = float(message.text.replace(',', '.'))
        await state.update_data(forced_downtime_rate=forced_downtime_rate)
        await message.answer("Введите примечания (или отправьте '-' если примечаний нет):")
        await DriverStates.waiting_for_notes.set()
    except ValueError:
        await message.answer("Ошибка! Введите число. Пример: 25.5")

@dp.message_handler(state=DriverStates.waiting_for_notes)
async def process_notes(message: types.Message, state: FSMContext):
    # Проверяем, не нажата ли кнопка "Назад"
    if message.text == "◀️ Назад":
        await state.finish()
        await message.answer("Действие отменено", reply_markup=get_drivers_keyboard())
        return
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
        f"⏱️ Обычный простой: {data['regular_downtime_rate']} руб/день\n"
        f"⏱️ Вынужденный простой: {data['forced_downtime_rate']} руб/день\n"
    )
    
    if notes:
        confirmation_text += f"📝 Примечания: {notes}\n"
    
    confirmation_text += "\nСохранить? (да/нет)"
    
    await message.answer(confirmation_text)
    await DriverStates.waiting_for_confirmation.set()

# Обработчик списка водителей
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
    
    # Формируем список водителей с инлайн-кнопками
    text = "📋 Список водителей:\n\n"
    
    for driver_id, name, km_rate in drivers:
        text += f"ID: {driver_id} | 👤 {name} | 💰 {km_rate} руб/км\n"
    
    text += "\nНажмите на имя водителя ниже, чтобы просмотреть детали:"
    
    # Создаем инлайн-клавиатуру для выбора водителя
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for driver_id, name, _ in drivers:
        keyboard.add(types.InlineKeyboardButton(
            f"👤 {name}", callback_data=f"driver_info_{driver_id}"
        ))
    
    # Отправляем одно сообщение с инлайн-клавиатурой
    await message.answer(text, reply_markup=keyboard)
    
    # Показываем обычную клавиатуру отдельным вызовом
    await message.answer("⌨️ Меню водителей", reply_markup=get_drivers_keyboard())
    
    conn.close()

# Обработчик для просмотра информации о водителе
@dp.callback_query_handler(lambda c: c.data.startswith('driver_info_'))
async def show_driver_info(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    
    driver_id = int(callback_query.data.split('_')[2])
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Проверяем структуру таблицы перед выполнением запроса
    cursor.execute("PRAGMA table_info(drivers)")
    columns = [column[1] for column in cursor.fetchall()]
    
    has_vehicle_id = 'vehicle_id' in columns
    
    if has_vehicle_id:
        # Получаем данные водителя с информацией о транспорте
        cursor.execute("""
            SELECT d.name, d.km_rate, d.side_loading_rate, d.roof_loading_rate,
                d.regular_downtime_rate, d.forced_downtime_rate, d.notes,
                v.truck_number, v.trailer_number
            FROM drivers d
            LEFT JOIN vehicles v ON d.vehicle_id = v.id
            WHERE d.id = ?
        """, (driver_id,))
    else:
        # Получаем данные водителя без информации о транспорте
        cursor.execute("""
            SELECT name, km_rate, side_loading_rate, roof_loading_rate,
                regular_downtime_rate, forced_downtime_rate, notes
            FROM drivers
            WHERE id = ?
        """, (driver_id,))
    
    driver_data = cursor.fetchone()
    
    if not driver_data:
        await bot.send_message(callback_query.from_user.id, "Водитель не найден!")
        conn.close()
        return
    
    # Формируем сообщение в зависимости от наличия столбца vehicle_id
    if has_vehicle_id:
        name, km_rate, side_rate, roof_rate, reg_rate, forced_rate, notes, truck, trailer = driver_data
    else:
        name, km_rate, side_rate, roof_rate, reg_rate, forced_rate, notes = driver_data
        truck, trailer = None, None
    
    # Формируем сообщение
    text = (
        f"📌 Информация о водителе\n"
        f"👤 Имя: {name}\n"
        f"💰 Ставка за км: {km_rate} руб\n"
        f"🚚 Боковой тент: {side_rate} руб\n"
        f"🚚 Крыша: {roof_rate} руб\n"
        f"⏱️ Обычный простой: {reg_rate} руб/день\n"
        f"⏱️ Вынужденный простой: {forced_rate} руб/день\n"
    )
    
    if has_vehicle_id and truck and trailer:
        text += f"🚛 Автопоезд: {truck}/{trailer}\n"
    else:
        text += "🚛 Автопоезд: не назначен\n"
    
    if notes:
        text += f"📝 Примечания: {notes}\n"
    
    # Создаем клавиатуру для редактирования
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_driver_{driver_id}")
    )
    
    # Добавляем кнопку назначения автопоезда только если колонка существует
    if has_vehicle_id:
        keyboard.add(types.InlineKeyboardButton("🚛 Назначить автопоезд", callback_data=f"assign_vehicle_{driver_id}"))
    else:
        # Если столбца нет, то предлагаем обновить БД
        keyboard.add(types.InlineKeyboardButton("🔄 Обновить базу данных", callback_data=f"update_db_structure"))
    
    keyboard.add(types.InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_driver_{driver_id}"))
    keyboard.add(types.InlineKeyboardButton("◀️ Назад к списку", callback_data="back_to_drivers_list"))
    
    # Отправляем ответ
    await bot.send_message(
        callback_query.from_user.id, 
        text, 
        reply_markup=keyboard
    )
    
    conn.close()

# Обработчик для кнопки "Назад к списку"
@dp.callback_query_handler(lambda c: c.data == "back_to_drivers_list")
async def back_to_drivers_list(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    
    # Создаем объект сообщения для передачи в функцию list_drivers
    message = types.Message.to_object({
        "message_id": 1,
        "date": 1,
        "chat": {"id": callback_query.from_user.id, "type": "private"},
        "from": {"id": callback_query.from_user.id},
        "text": "📋 Список водителей"
    })
    
    # Вызываем функцию для отображения списка водителей
    await list_drivers(message)

# Обработчик для обновления структуры БД
@dp.callback_query_handler(lambda c: c.data == "update_db_structure")
async def update_db_structure(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE drivers ADD COLUMN vehicle_id INTEGER")
        conn.commit()
        await bot.send_message(
            callback_query.from_user.id,
            "✅ База данных успешно обновлена! Теперь вы можете назначать автопоезда водителям.",
            reply_markup=get_drivers_keyboard()
        )
    except sqlite3.OperationalError:
        await bot.send_message(
            callback_query.from_user.id,
            "❌ Не удалось обновить базу данных. Возможно, она уже обновлена.",
            reply_markup=get_drivers_keyboard()
        )
    
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

# Новые состояния для редактирования водителей
class DriverEditStates(StatesGroup):
    waiting_for_driver_id = State()
    waiting_for_field = State()
    waiting_for_new_value = State()
    waiting_for_confirmation = State()

# Обработчик для редактирования водителя
@dp.callback_query_handler(lambda c: c.data.startswith('edit_driver_'))
async def edit_driver(callback_query: types.CallbackQuery):
    driver_id = int(callback_query.data.split('_')[2])
    
    # Создаем клавиатуру для выбора поля для редактирования
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("👤 Имя", callback_data=f"edit_field_{driver_id}_name"),
        types.InlineKeyboardButton("💰 Ставка за км", callback_data=f"edit_field_{driver_id}_km_rate"),
        types.InlineKeyboardButton("🚚 Боковой тент", callback_data=f"edit_field_{driver_id}_side_loading_rate"),
        types.InlineKeyboardButton("🚚 Крыша", callback_data=f"edit_field_{driver_id}_roof_loading_rate"),
        types.InlineKeyboardButton("⏱️ Обычный простой", callback_data=f"edit_field_{driver_id}_regular_downtime_rate"),
        types.InlineKeyboardButton("⏱️ Вынужденный простой", callback_data=f"edit_field_{driver_id}_forced_downtime_rate"),
        types.InlineKeyboardButton("📝 Примечания", callback_data=f"edit_field_{driver_id}_notes")
    )
    
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id, 
        "Выберите поле для редактирования:", 
        reply_markup=keyboard
    )

# Обработчик для выбора поля для редактирования
@dp.callback_query_handler(lambda c: c.data.startswith('edit_field_'))
async def edit_field(callback_query: types.CallbackQuery, state: FSMContext):
    parts = callback_query.data.split('_')
    driver_id = int(parts[2])
    field = parts[3]
    
    # Сохраняем информацию о водителе и поле
    await state.update_data(driver_id=driver_id, field=field)
    
    # Определяем сообщение в зависимости от поля
    field_names = {
        "name": "имя",
        "km_rate": "ставку за километр (в рублях)",
        "side_loading_rate": "ставку за погрузку/разгрузку бокового тента (в рублях)",
        "roof_loading_rate": "ставку за погрузку/разгрузку крыши (в рублях)",
        "regular_downtime_rate": "ставку за обычный простой (в рублях/день)",
        "forced_downtime_rate": "ставку за вынужденный простой (в рублях/день)",
        "notes": "примечания"
    }
    
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        f"Введите новое значение для поля '{field_names.get(field, field)}':"
    )
    
    await DriverEditStates.waiting_for_new_value.set()

# Обработчик для ввода нового значения
@dp.message_handler(state=DriverEditStates.waiting_for_new_value)
async def process_new_value(message: types.Message, state: FSMContext):
    # Проверяем, не нажата ли кнопка "Назад"
    if message.text == "◀️ Назад":
        await state.finish()
        await message.answer("Действие отменено", reply_markup=get_drivers_keyboard())
        return
    data = await state.get_data()
    driver_id = data.get('driver_id')
    field = data.get('field')
    
    # Проверяем и обрабатываем значение в зависимости от поля
    try:
        if field in ['km_rate', 'side_loading_rate', 'roof_loading_rate', 
                    'regular_downtime_rate', 'forced_downtime_rate']:
            new_value = float(message.text.replace(',', '.'))
        else:
            new_value = message.text
    except ValueError:
        await message.answer("Ошибка! Введите число.")
        return
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Обновляем данные в базе
    cursor.execute(
        f"UPDATE drivers SET {field} = ? WHERE id = ?",
        (new_value, driver_id)
    )
    
    # Логируем действие
    cursor.execute(
        "INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)",
        (message.from_user.id, "Редактирование водителя", 
         f"Водитель ID#{driver_id}, изменено поле {field} на {new_value}")
    )
    
    conn.commit()
    
    # Получаем обновленные данные
    cursor.execute("SELECT name FROM drivers WHERE id = ?", (driver_id,))
    driver_name = cursor.fetchone()[0]
    
    conn.close()
    
    await message.answer(
        f"✅ Данные водителя {driver_name} успешно обновлены!",
        reply_markup=get_drivers_keyboard()
    )
    await state.finish()

# Обработчик для назначения автопоезда водителю
@dp.callback_query_handler(lambda c: c.data.startswith('assign_vehicle_'))
async def assign_vehicle(callback_query: types.CallbackQuery):
    driver_id = int(callback_query.data.split('_')[2])
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Проверяем структуру таблицы перед выполнением запроса
    cursor.execute("PRAGMA table_info(drivers)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'vehicle_id' not in columns:
        # Если колонки нет, добавляем ее
        try:
            cursor.execute("ALTER TABLE drivers ADD COLUMN vehicle_id INTEGER")
            conn.commit()
            await bot.send_message(
                callback_query.from_user.id,
                "✅ База данных обновлена: добавлена поддержка автопоездов!"
            )
        except sqlite3.OperationalError:
            # Колонка уже существует или другая ошибка
            pass
    
    # Получаем список автопоездов
    cursor.execute("SELECT id, truck_number, trailer_number FROM vehicles ORDER BY truck_number")
    vehicles = cursor.fetchall()
    
    if not vehicles:
        await bot.answer_callback_query(callback_query.id, "Нет доступных автопоездов!")
        await bot.send_message(
            callback_query.from_user.id,
            "Список автопоездов пуст. Добавьте автопоезда в разделе Управление → Автопоезда.",
            reply_markup=get_drivers_keyboard()
        )
        conn.close()
        return
    
    # Создаем клавиатуру для выбора автопоезда
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for vehicle_id, truck, trailer in vehicles:
        keyboard.add(types.InlineKeyboardButton(
            f"{truck}/{trailer}", callback_data=f"set_vehicle_{driver_id}_{vehicle_id}"
        ))
    
    # Добавляем кнопку для отмены назначения
    keyboard.add(types.InlineKeyboardButton(
        "❌ Отменить назначение", callback_data=f"set_vehicle_{driver_id}_0"
    ))
    
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        "Выберите автопоезд для водителя:",
        reply_markup=keyboard
    )
    
    conn.close()

# Обработчик для установки автопоезда
@dp.callback_query_handler(lambda c: c.data.startswith('set_vehicle_'))
async def set_vehicle(callback_query: types.CallbackQuery):
    parts = callback_query.data.split('_')
    driver_id = int(parts[2])
    vehicle_id = int(parts[3])
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Проверяем структуру таблицы перед выполнением запроса
    cursor.execute("PRAGMA table_info(drivers)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'vehicle_id' not in columns:
        # Если колонки нет, добавляем ее
        try:
            cursor.execute("ALTER TABLE drivers ADD COLUMN vehicle_id INTEGER")
            conn.commit()
        except sqlite3.OperationalError:
            # Колонка уже существует или другая ошибка
            pass
    
    # Получаем имя водителя
    cursor.execute("SELECT name FROM drivers WHERE id = ?", (driver_id,))
    driver_name = cursor.fetchone()[0]
    
    # Обновляем привязку автопоезда
    if vehicle_id == 0:
        # Отменяем привязку
        cursor.execute("UPDATE drivers SET vehicle_id = NULL WHERE id = ?", (driver_id,))
        vehicle_info = "отменено"
    else:
        # Устанавливаем привязку
        cursor.execute("UPDATE drivers SET vehicle_id = ? WHERE id = ?", (vehicle_id, driver_id))
        
        # Получаем информацию об автопоезде
        cursor.execute("SELECT truck_number, trailer_number FROM vehicles WHERE id = ?", (vehicle_id,))
        truck, trailer = cursor.fetchone()
        vehicle_info = f"{truck}/{trailer}"
    
    # Логируем действие
    cursor.execute(
        "INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)",
        (callback_query.from_user.id, "Назначение автопоезда", 
         f"Водителю {driver_name} (ID#{driver_id}) назначен автопоезд {vehicle_info}")
    )
    
    conn.commit()
    conn.close()
    
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        f"✅ Автопоезд для водителя {driver_name} {vehicle_info if vehicle_id != 0 else 'не назначен'}.",
        reply_markup=get_drivers_keyboard()
    )

# Обработчик для удаления водителя
@dp.callback_query_handler(lambda c: c.data.startswith('delete_driver_'))
async def delete_driver(callback_query: types.CallbackQuery):
    driver_id = int(callback_query.data.split('_')[2])
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Получаем имя водителя
    cursor.execute("SELECT name FROM drivers WHERE id = ?", (driver_id,))
    driver_result = cursor.fetchone()
    
    if not driver_result:
        await bot.answer_callback_query(callback_query.id, "Водитель не найден!")
        conn.close()
        return
    
    driver_name = driver_result[0]
    
    # Клавиатура для подтверждения
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{driver_id}"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_delete")
    )
    
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        f"⚠️ Вы уверены, что хотите удалить водителя {driver_name}?",
        reply_markup=keyboard
    )
    
    conn.close()

# Обработчик для подтверждения удаления
@dp.callback_query_handler(lambda c: c.data.startswith('confirm_delete_'))
async def confirm_delete_driver(callback_query: types.CallbackQuery):
    driver_id = int(callback_query.data.split('_')[2])
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Получаем имя водителя
    cursor.execute("SELECT name FROM drivers WHERE id = ?", (driver_id,))
    driver_result = cursor.fetchone()
    
    if not driver_result:
        await bot.answer_callback_query(callback_query.id, "Водитель не найден!")
        conn.close()
        return
    
    driver_name = driver_result[0]
    
    # Удаляем водителя
    cursor.execute("DELETE FROM drivers WHERE id = ?", (driver_id,))
    
    # Логируем действие
    cursor.execute(
        "INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)",
        (callback_query.from_user.id, "Удаление водителя", f"Удален водитель: {driver_name}")
    )
    
    conn.commit()
    conn.close()
    
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        f"✅ Водитель {driver_name} успешно удален!",
        reply_markup=get_drivers_keyboard()
    )

# Обработчик для отмены удаления
@dp.callback_query_handler(lambda c: c.data == "cancel_delete")
async def cancel_delete(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        "❌ Удаление отменено.",
        reply_markup=get_drivers_keyboard()
    )
