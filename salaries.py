# salaries.py
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot import dp, bot, check_user_access
import sqlite3
from datetime import datetime, timedelta
import io
import csv
import logging

# Класс состояний для ввода ID рейса, который нужно отметить оплаченным
class PaymentStates(StatesGroup):
    waiting_for_trip_id = State()

# Класс состояний для ввода суммы оплаты
class PaymentAmountStates(StatesGroup):
    waiting_for_trip_id = State()
    waiting_for_amount = State()

# Проверяем и обновляем структуру базы данных
def check_db_structure():
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Проверяем существующие колонки в таблице trips
    cursor.execute("PRAGMA table_info(trips)")
    columns = [column[1] for column in cursor.fetchall()]
    
    # Проверяем и добавляем колонку paid, если ее нет
    if 'paid' not in columns:
        try:
            cursor.execute("ALTER TABLE trips ADD COLUMN paid INTEGER DEFAULT 0")
            conn.commit()
            logging.info("База данных обновлена: добавлена колонка 'paid' в таблицу 'trips'")
        except sqlite3.OperationalError as e:
            logging.error(f"Ошибка обновления структуры БД: {e}")
    
    # Проверяем и добавляем колонку paid_amount, если ее нет
    if 'paid_amount' not in columns:
        try:
            cursor.execute("ALTER TABLE trips ADD COLUMN paid_amount REAL DEFAULT 0")
            conn.commit()
            logging.info("База данных обновлена: добавлена колонка 'paid_amount' в таблицу 'trips'")
        except sqlite3.OperationalError as e:
            logging.error(f"Ошибка обновления структуры БД: {e}")
    
    conn.close()

# Вызываем функцию проверки структуры БД при импорте модуля
check_db_structure()

# Обработчик для показа актуальных данных
@dp.message_handler(lambda message: message.text == "📊 Актуальные данные")
async def show_current_data(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=2):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    # Получаем количество неоплаченных рейсов
    cursor.execute("SELECT COUNT(*) FROM trips WHERE paid = 0")
    unpaid_count = cursor.fetchone()[0]
    
    # Получаем общую сумму задолженности с учетом частичной оплаты
    cursor.execute("SELECT SUM(total_payment - paid_amount) FROM trips WHERE paid = 0")
    total_debt = cursor.fetchone()[0] or 0
    
    # Создаем клавиатуру для отображения задолженностей
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(f"💰 Задолженности по зарплате ({unpaid_count} рейсов, {int(total_debt)} ₽)", 
                            callback_data="view_debts"),
        InlineKeyboardButton("👤 Задолженности по водителям", callback_data="view_debts_by_driver"),
        InlineKeyboardButton("📊 Детальный отчёт", callback_data="detailed_report")
    )
    
    await message.answer(
        "📊 Выберите отчет для просмотра:\n\n"
        f"Всего неоплаченных рейсов: {unpaid_count}\n"
        f"Общая сумма задолженности: {int(total_debt)} ₽",
        reply_markup=keyboard
    )
    
    conn.close()

# Обработчик для просмотра всех задолженностей
@dp.callback_query_handler(lambda c: c.data == "view_debts")
async def view_debts(callback_query: types.CallbackQuery):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Получаем неоплаченные рейсы (полностью или частично)
        cursor.execute("""
        SELECT t.id, d.name, t.loading_city, t.unloading_city, 
               t.distance, t.total_payment, t.paid_amount, t.created_at
        FROM trips t
        JOIN drivers d ON t.driver_id = d.id
        WHERE t.paid = 0
        ORDER BY t.created_at DESC
        """)
        
        unpaid_trips = cursor.fetchall()
        
        if not unpaid_trips:
            await bot.answer_callback_query(callback_query.id)
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text="Нет неоплаченных рейсов."
            )
            conn.close()
            return
        
        # Формируем сообщение с задолженностями
        text = "💰 Неоплаченные рейсы:\n\n"
        
        total_debt = 0
        for trip_id, driver_name, load_city, unload_city, distance, payment, paid_amount, date in unpaid_trips:
            trip_date = date.split(' ')[0]  # Берем только дату без времени
            remaining = payment - paid_amount
            payment_status = f"Частично оплачено: {int(paid_amount)} ₽" if paid_amount > 0 else "Не оплачено"
            
            text += (
                f"🔹 Рейс #{trip_id} ({trip_date})\n"
                f"👤 Водитель: {driver_name}\n"
                f"🚚 Маршрут: {load_city} → {unload_city}\n"
                f"💵 Сумма: {int(payment)} ₽ ({payment_status})\n"
                f"💸 Осталось: {int(remaining)} ₽\n\n"
            )
            total_debt += remaining
        
        # Добавляем итоговую сумму
        text += f"Итого задолженность: {int(total_debt)} ₽"
        
        # Создаем клавиатуру с действиями
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("✅ Отметить рейс как полностью оплаченный", callback_data="mark_paid"),
            InlineKeyboardButton("💵 Внести частичную оплату", callback_data="partial_payment"),
            InlineKeyboardButton("📋 Экспорт в CSV", callback_data="export_debts"),
            InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
        )
        
        await bot.answer_callback_query(callback_query.id)
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=text,
            reply_markup=keyboard
        )
    
    except Exception as e:
        logging.error(f"Ошибка при получении данных о задолженностях: {str(e)}")
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.message.chat.id,
            f"❌ Ошибка при получении данных: {str(e)}"
        )
    
    finally:
        conn.close()

# Обработчик для отображения задолженностей по водителям
@dp.callback_query_handler(lambda c: c.data == "view_debts_by_driver")
async def view_debts_by_driver(callback_query: types.CallbackQuery):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Получаем задолженности по водителям
        cursor.execute("""
        SELECT d.id, d.name, COUNT(t.id) as trips_count, 
               SUM(t.total_payment - t.paid_amount) as total_debt
        FROM drivers d
        LEFT JOIN trips t ON d.id = t.driver_id AND t.paid = 0
        GROUP BY d.id
        HAVING trips_count > 0
        ORDER BY total_debt DESC
        """)
        
        driver_debts = cursor.fetchall()
        
        if not driver_debts:
            await bot.answer_callback_query(callback_query.id)
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text="Нет задолженностей по водителям."
            )
            conn.close()
            return
        
        # Формируем сообщение с задолженностями по водителям
        text = "👤 Задолженности по водителям:\n\n"
        
        for driver_id, name, trips_count, total_debt in driver_debts:
            text += (
                f"👤 {name}\n"
                f"🚚 Рейсов: {trips_count}\n"
                f"💵 Сумма: {int(total_debt)} руб.\n\n"
            )
        
        # Создаем клавиатуру для выбора водителя
        keyboard = InlineKeyboardMarkup(row_width=1)
        for driver_id, name, _, _ in driver_debts:
            keyboard.add(InlineKeyboardButton(
                f"{name} - детали", callback_data=f"driver_trips_{driver_id}"
            ))
        
        keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data="back_to_main"))
        
        await bot.answer_callback_query(callback_query.id)
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=text,
            reply_markup=keyboard
        )
    
    except Exception as e:
        logging.error(f"Ошибка при получении задолженностей по водителям: {str(e)}")
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.message.chat.id,
            f"❌ Ошибка при получении данных: {str(e)}"
        )
    
    finally:
        conn.close()

# Обработчик для отображения неоплаченных рейсов конкретного водителя
@dp.callback_query_handler(lambda c: c.data.startswith("driver_trips_"))
async def view_driver_trips(callback_query: types.CallbackQuery):
    driver_id = int(callback_query.data.split("_")[2])
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Получаем имя водителя
        cursor.execute("SELECT name FROM drivers WHERE id = ?", (driver_id,))
        driver_name = cursor.fetchone()[0]
        
        # Получаем неоплаченные рейсы водителя
        cursor.execute("""
        SELECT id, loading_city, unloading_city, 
               distance, total_payment, created_at
        FROM trips
        WHERE driver_id = ? AND paid = 0
        ORDER BY created_at DESC
        """, (driver_id,))
        
        trips = cursor.fetchall()
        
        if not trips:
            await bot.answer_callback_query(callback_query.id)
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=f"У водителя {driver_name} нет неоплаченных рейсов.",
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("◀️ Назад", callback_data="view_debts_by_driver")
                )
            )
            conn.close()
            return
        
        # Формируем сообщение с рейсами водителя
        text = f"👤 Неоплаченные рейсы водителя {driver_name}:\n\n"
        
        total_debt = 0
        for trip_id, load_city, unload_city, distance, payment, date in trips:
            trip_date = date.split(' ')[0]
            text += (
                f"🔹 Рейс #{trip_id} ({trip_date})\n"
                f"🚚 Маршрут: {load_city} → {unload_city}\n"
                f"📏 Расстояние: {distance} км\n"
                f"💵 Сумма: {int(payment)} руб.\n\n"
            )
            total_debt += payment
        
        text += f"Итого: {int(total_debt)} руб."
        
        # Создаем клавиатуру с рейсами для отметки как оплаченных
        keyboard = InlineKeyboardMarkup(row_width=1)
        for trip_id, _, _, _, payment, _ in trips:
            keyboard.add(InlineKeyboardButton(
                f"✅ Отметить рейс #{trip_id} как оплаченный ({int(payment)} руб.)", 
                callback_data=f"pay_trip_{trip_id}"
            ))
        
        keyboard.add(InlineKeyboardButton(
            f"✅ Отметить ВСЕ рейсы водителя как оплаченные", 
            callback_data=f"pay_all_driver_{driver_id}"
        ))
        keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data="view_debts_by_driver"))
        
        await bot.answer_callback_query(callback_query.id)
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=text,
            reply_markup=keyboard
        )
    
    except Exception as e:
        logging.error(f"Ошибка при получении рейсов водителя: {str(e)}")
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.message.chat.id,
            f"❌ Ошибка при получении данных: {str(e)}"
        )
    
    finally:
        conn.close()

# Обработчик для отметки рейса как оплаченного
@dp.callback_query_handler(lambda c: c.data.startswith("pay_trip_"))
async def mark_trip_paid(callback_query: types.CallbackQuery):
    trip_id = int(callback_query.data.split("_")[2])
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Получаем информацию о рейсе
        cursor.execute("""
        SELECT t.id, d.name, t.loading_city, t.unloading_city, t.total_payment
        FROM trips t
        JOIN drivers d ON t.driver_id = d.id
        WHERE t.id = ?
        """, (trip_id,))
        
        trip = cursor.fetchone()
        
        if not trip:
            await bot.answer_callback_query(callback_query.id, text="Рейс не найден!")
            conn.close()
            return
        
        trip_id, driver_name, load_city, unload_city, payment = trip
        
        # Отмечаем рейс как оплаченный
        cursor.execute("UPDATE trips SET paid = 1 WHERE id = ?", (trip_id,))
        
        # Логируем действие
        cursor.execute(
            "INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)",
            (
                callback_query.from_user.id,
                "Отметка рейса как оплаченного",
                f"Рейс #{trip_id}: {driver_name}, {load_city}-{unload_city}, {payment} руб."
            )
        )
        
        conn.commit()
        
        await bot.answer_callback_query(callback_query.id, text="✅ Рейс отмечен как оплаченный!")
        
        # Возвращаемся к списку задолженностей по водителям
        await view_debts_by_driver(callback_query)
    
    except Exception as e:
        logging.error(f"Ошибка при отметке рейса как оплаченного: {str(e)}")
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.message.chat.id,
            f"❌ Ошибка при отметке рейса: {str(e)}"
        )
    
    finally:
        conn.close()

# Обработчик для выбора рейса для частичной оплаты
@dp.callback_query_handler(lambda c: c.data == "partial_payment")
async def select_trip_for_partial_payment(callback_query: types.CallbackQuery):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Получаем неоплаченные рейсы
        cursor.execute("""
        SELECT t.id, d.name, t.loading_city, t.unloading_city, 
               t.total_payment, t.paid_amount
        FROM trips t
        JOIN drivers d ON t.driver_id = d.id
        WHERE t.paid = 0
        ORDER BY t.created_at DESC
        """)
        
        trips = cursor.fetchall()
        
        if not trips:
            await bot.answer_callback_query(callback_query.id, text="Нет неоплаченных рейсов!")
            await view_debts(callback_query)
            conn.close()
            return
        
        # Создаем клавиатуру для выбора рейса
        keyboard = InlineKeyboardMarkup(row_width=1)
        
        for trip_id, driver, load, unload, payment, paid_amount in trips:
            remaining = payment - paid_amount
            status = f"(уже оплачено: {int(paid_amount)} ₽)" if paid_amount > 0 else ""
            keyboard.add(InlineKeyboardButton(
                f"#{trip_id}: {driver}, {load}-{unload}, долг: {int(remaining)} ₽ {status}",
                callback_data=f"partial_pay_trip_{trip_id}"
            ))
        
        keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data="view_debts"))
        
        await bot.answer_callback_query(callback_query.id)
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="Выберите рейс для внесения частичной оплаты:",
            reply_markup=keyboard
        )
    
    except Exception as e:
        logging.error(f"Ошибка при выборе рейса для частичной оплаты: {str(e)}")
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.message.chat.id,
            f"❌ Ошибка: {str(e)}"
        )
    
    finally:
        conn.close()

# Обработчик для выбора рейса для частичной оплаты
@dp.callback_query_handler(lambda c: c.data.startswith("partial_pay_trip_"))
async def enter_partial_payment_amount(callback_query: types.CallbackQuery, state: FSMContext):
    trip_id = int(callback_query.data.split("_")[3])
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Получаем информацию о рейсе
        cursor.execute("""
        SELECT t.id, d.name, t.loading_city, t.unloading_city, 
               t.total_payment, t.paid_amount
        FROM trips t
        JOIN drivers d ON t.driver_id = d.id
        WHERE t.id = ?
        """, (trip_id,))
        
        trip = cursor.fetchone()
        
        if not trip:
            await bot.answer_callback_query(callback_query.id, text="Рейс не найден!")
            conn.close()
            return
        
        _, driver_name, load_city, unload_city, total_payment, paid_amount = trip
        remaining = total_payment - paid_amount
        
        # Сохраняем данные в состоянии
        await state.update_data(
            trip_id=trip_id,
            driver_name=driver_name,
            load_city=load_city,
            unload_city=unload_city,
            total_payment=total_payment,
            paid_amount=paid_amount,
            remaining=remaining
        )
        
        await PaymentAmountStates.waiting_for_amount.set()
        
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.message.chat.id,
            f"Введите сумму частичной оплаты для рейса #{trip_id}:\n\n"
            f"👤 Водитель: {driver_name}\n"
            f"🚚 Маршрут: {load_city} → {unload_city}\n"
            f"💵 Общая сумма: {int(total_payment)} ₽\n"
            f"💵 Уже оплачено: {int(paid_amount)} ₽\n"
            f"💸 Осталось оплатить: {int(remaining)} ₽\n\n"
            f"Введите сумму (целое число):"
        )
    
    except Exception as e:
        logging.error(f"Ошибка при выборе рейса для частичной оплаты: {str(e)}")
        await bot.send_message(
            callback_query.message.chat.id,
            f"❌ Ошибка: {str(e)}"
        )
        await state.finish()
    
    finally:
        conn.close()

# Обработчик ввода суммы частичной оплаты
@dp.message_handler(state=PaymentAmountStates.waiting_for_amount)
async def process_payment_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        data = await state.get_data()
        
        trip_id = data['trip_id']
        total_payment = data['total_payment']
        paid_amount = data['paid_amount']
        remaining = data['remaining']
        driver_name = data['driver_name']
        load_city = data['load_city']
        unload_city = data['unload_city']
        
        if amount <= 0:
            await message.answer("Сумма оплаты должна быть положительным числом.")
            return
        
        if amount > remaining:
            await message.answer(f"Введенная сумма ({amount} ₽) превышает оставшуюся задолженность ({int(remaining)} ₽).\n"
                                f"Желаете отметить рейс как полностью оплаченный?",
                                reply_markup=InlineKeyboardMarkup().add(
                                    InlineKeyboardButton("Да", callback_data=f"confirm_full_payment_{trip_id}"),
                                    InlineKeyboardButton("Нет", callback_data="cancel_payment")
                                ))
            await state.finish()
            return
        
        conn = sqlite3.connect('salary_bot.db')
        cursor = conn.cursor()
        
        # Обновляем сумму оплаты
        new_paid_amount = paid_amount + amount
        is_fully_paid = (new_paid_amount >= total_payment)
        
        # Если рейс полностью оплачен, отмечаем его как оплаченный
        if is_fully_paid:
            cursor.execute(
                "UPDATE trips SET paid = 1, paid_amount = ? WHERE id = ?", 
                (total_payment, trip_id)
            )
            status_text = "полностью оплачен"
        else:
            cursor.execute(
                "UPDATE trips SET paid_amount = ? WHERE id = ?", 
                (new_paid_amount, trip_id)
            )
            status_text = f"частично оплачен (внесено {int(new_paid_amount)} ₽ из {int(total_payment)} ₽)"
        
        # Логируем действие
        cursor.execute(
            "INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)",
            (
                message.from_user.id,
                "Частичная оплата рейса" if not is_fully_paid else "Полная оплата рейса",
                f"Рейс #{trip_id}: {driver_name}, {load_city}-{unload_city}, внесено {amount} ₽"
            )
        )
        
        conn.commit()
        conn.close()
        
        await message.answer(
            f"✅ Оплата в размере {amount} ₽ внесена для рейса #{trip_id}!\n\n"
            f"👤 Водитель: {driver_name}\n"
            f"🚚 Маршрут: {load_city} → {unload_city}\n"
            f"💵 Общая сумма: {int(total_payment)} ₽\n"
            f"💵 Оплачено: {int(new_paid_amount)} ₽\n"
            f"💸 Осталось: {int(total_payment - new_paid_amount)} ₽\n\n"
            f"Статус рейса: {status_text}"
        )
        
    except ValueError:
        await message.answer("Некорректная сумма. Пожалуйста, введите целое число.")
        return
    except Exception as e:
        logging.error(f"Ошибка при обработке частичной оплаты: {str(e)}")
        await message.answer(f"❌ Ошибка при обработке оплаты: {str(e)}")
    
    finally:
        await state.finish()

# Обработчик для подтверждения полной оплаты
@dp.callback_query_handler(lambda c: c.data.startswith("confirm_full_payment_"))
async def confirm_full_payment(callback_query: types.CallbackQuery):
    trip_id = int(callback_query.data.split("_")[3])
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Получаем информацию о рейсе
        cursor.execute("""
        SELECT t.id, d.name, t.loading_city, t.unloading_city, t.total_payment
        FROM trips t
        JOIN drivers d ON t.driver_id = d.id
        WHERE t.id = ?
        """, (trip_id,))
        
        trip = cursor.fetchone()
        
        if not trip:
            await bot.answer_callback_query(callback_query.id, text="Рейс не найден!")
            conn.close()
            return
        
        trip_id, driver_name, load_city, unload_city, total_payment = trip
        
        # Отмечаем рейс как полностью оплаченный
        cursor.execute(
            "UPDATE trips SET paid = 1, paid_amount = ? WHERE id = ?", 
            (total_payment, trip_id)
        )
        
        # Логируем действие
        cursor.execute(
            "INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)",
            (
                callback_query.from_user.id,
                "Полная оплата рейса",
                f"Рейс #{trip_id}: {driver_name}, {load_city}-{unload_city}, {total_payment} руб."
            )
        )
        
        conn.commit()
        
        await bot.answer_callback_query(callback_query.id, text="✅ Рейс отмечен как полностью оплаченный!")
        await bot.send_message(
            callback_query.message.chat.id,
            f"✅ Рейс #{trip_id} отмечен как полностью оплаченный!\n\n"
            f"👤 Водитель: {driver_name}\n"
            f"🚚 Маршрут: {load_city} → {unload_city}\n"
            f"💵 Сумма: {int(total_payment)} ₽"
        )
    
    except Exception as e:
        logging.error(f"Ошибка при отметке рейса как оплаченного: {str(e)}")
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.message.chat.id,
            f"❌ Ошибка при отметке рейса: {str(e)}"
        )
    
    finally:
        conn.close()

# Обработчик для отмены оплаты
@dp.callback_query_handler(lambda c: c.data == "cancel_payment")
async def cancel_payment(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.message.chat.id,
        "🚫 Оплата отменена."
    )

# Обработчик для отметки всех рейсов водителя как оплаченных
@dp.callback_query_handler(lambda c: c.data.startswith("pay_all_driver_"))
async def mark_all_driver_trips_paid(callback_query: types.CallbackQuery):
    driver_id = int(callback_query.data.split("_")[3])
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Получаем имя водителя
        cursor.execute("SELECT name FROM drivers WHERE id = ?", (driver_id,))
        driver_name = cursor.fetchone()[0]
        
        # Получаем количество и общую сумму неоплаченных рейсов
        cursor.execute("""
        SELECT COUNT(*), SUM(total_payment)
        FROM trips
        WHERE driver_id = ? AND paid = 0
        """, (driver_id,))
        
        count, total = cursor.fetchone()
        
        if not count or count == 0:
            await bot.answer_callback_query(callback_query.id, text="Нет неоплаченных рейсов!")
            conn.close()
            return
        
        # Отмечаем все рейсы водителя как оплаченные
        cursor.execute("UPDATE trips SET paid = 1 WHERE driver_id = ? AND paid = 0", (driver_id,))
        
        # Логируем действие
        cursor.execute(
            "INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)",
            (
                callback_query.from_user.id,
                "Отметка всех рейсов водителя как оплаченных",
                f"Водитель: {driver_name}, Рейсов: {count}, Сумма: {total} руб."
            )
        )
        
        conn.commit()
        
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.message.chat.id,
            f"✅ Все рейсы водителя {driver_name} отмечены как оплаченные!\n"
            f"Количество рейсов: {count}\n"
            f"Общая сумма: {int(total)} руб."
        )
        
        # Возвращаемся к списку задолженностей по водителям
        await view_debts_by_driver(callback_query)
    
    except Exception as e:
        logging.error(f"Ошибка при отметке всех рейсов водителя: {str(e)}")
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.message.chat.id,
            f"❌ Ошибка при отметке рейсов: {str(e)}"
        )
    
    finally:
        conn.close()

# Обработчик для выбора рейса, который нужно отметить как оплаченный
@dp.callback_query_handler(lambda c: c.data == "mark_paid")
async def select_trip_to_mark_paid(callback_query: types.CallbackQuery):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Получаем неоплаченные рейсы
        cursor.execute("""
        SELECT t.id, d.name, t.loading_city, t.unloading_city, t.total_payment
        FROM trips t
        JOIN drivers d ON t.driver_id = d.id
        WHERE t.paid = 0
        ORDER BY t.created_at DESC
        """)
        
        trips = cursor.fetchall()
        
        if not trips:
            await bot.answer_callback_query(callback_query.id, text="Нет неоплаченных рейсов!")
            await view_debts(callback_query)
            conn.close()
            return
        
        # Создаем клавиатуру для выбора рейса
        keyboard = InlineKeyboardMarkup(row_width=1)
        
        for trip_id, driver, load, unload, payment in trips:
            keyboard.add(InlineKeyboardButton(
                f"#{trip_id}: {driver}, {load}-{unload}, {int(payment)} руб.",
                callback_data=f"pay_trip_{trip_id}"
            ))
        
        keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data="view_debts"))
        
        await bot.answer_callback_query(callback_query.id)
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="Выберите рейс, который нужно отметить как оплаченный:",
            reply_markup=keyboard
        )
    
    except Exception as e:
        logging.error(f"Ошибка при выборе рейса для оплаты: {str(e)}")
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.message.chat.id,
            f"❌ Ошибка: {str(e)}"
        )
    
    finally:
        conn.close()

# Обработчик для экспорта задолженностей в CSV
@dp.callback_query_handler(lambda c: c.data == "export_debts")
async def export_debts(callback_query: types.CallbackQuery):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Получаем неоплаченные рейсы
        cursor.execute("""
        SELECT t.id, d.name, v.truck_number, v.trailer_number,
               t.loading_city, t.unloading_city, t.distance,
               t.side_loading_count, t.roof_loading_count,
               t.total_payment, t.paid_amount, (t.total_payment - t.paid_amount) as remaining, t.created_at
        FROM trips t
        JOIN drivers d ON t.driver_id = d.id
        JOIN vehicles v ON t.vehicle_id = v.id
        WHERE t.paid = 0
        ORDER BY d.name, t.created_at
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
            "Крыша", "Общая сумма (руб)", "Оплачено (руб)", "Осталось (руб)", "Дата"
        ])
        
        # Данные
        for trip in trips:
            writer.writerow(trip)
        
        # Конвертируем в байты
        csv_bytes = output.getvalue().encode('utf-8-sig')
        
        # Отправляем файл
        filename = f"unpaid_trips_{datetime.now().strftime('%Y-%m-%d')}.csv"
        
        await bot.answer_callback_query(callback_query.id)
        await bot.send_document(
            callback_query.message.chat.id,
            (filename, io.BytesIO(csv_bytes)),
            caption="Отчет по неоплаченным рейсам"
        )
    
    except Exception as e:
        logging.error(f"Ошибка при экспорте неоплаченных рейсов: {str(e)}")
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.message.chat.id,
            f"❌ Ошибка при экспорте: {str(e)}"
        )
    
    finally:
        conn.close()

# Обработчик для возврата к главному меню
@dp.callback_query_handler(lambda c: c.data == "back_to_main")
async def back_to_main_menu(callback_query: types.CallbackQuery):
    # Создаем искусственное сообщение для вызова show_current_data
    message = types.Message.to_object({
        "message_id": callback_query.message.message_id,
        "from": callback_query.from_user.to_python(),
        "chat": callback_query.message.chat.to_python(),
        "date": datetime.now().timestamp(),
        "text": "📊 Актуальные данные"
    })
    
    await bot.answer_callback_query(callback_query.id)
    await bot.delete_message(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id
    )
    await show_current_data(message)

# Обработчик для отображения детального отчета
@dp.callback_query_handler(lambda c: c.data == "detailed_report")
async def show_detailed_report(callback_query: types.CallbackQuery):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Получаем статистику по водителям с учетом частичной оплаты
        cursor.execute("""
        SELECT d.name, 
               COUNT(CASE WHEN t.paid = 0 THEN 1 ELSE NULL END) as unpaid_trips,
               SUM(CASE WHEN t.paid = 0 THEN (t.total_payment - t.paid_amount) ELSE 0 END) as unpaid_amount,
               SUM(CASE WHEN t.paid = 0 THEN t.paid_amount ELSE 0 END) as partially_paid_amount,
               COUNT(CASE WHEN t.paid = 1 THEN 1 ELSE NULL END) as paid_trips,
               SUM(CASE WHEN t.paid = 1 THEN t.total_payment ELSE 0 END) as paid_amount,
               COUNT(t.id) as total_trips,
               SUM(t.total_payment) as total_amount
        FROM drivers d
        LEFT JOIN trips t ON d.id = t.driver_id
        GROUP BY d.id
        ORDER BY unpaid_amount DESC
        """)
        
        driver_stats = cursor.fetchall()
        
        if not driver_stats:
            await bot.answer_callback_query(callback_query.id)
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text="Нет данных для отчета."
            )
            conn.close()
            return
        
        # Получаем общую статистику с учетом частичной оплаты
        cursor.execute("""
        SELECT COUNT(CASE WHEN paid = 0 THEN 1 ELSE NULL END) as unpaid_trips,
               SUM(CASE WHEN paid = 0 THEN (total_payment - paid_amount) ELSE 0 END) as unpaid_amount,
               SUM(CASE WHEN paid = 0 THEN paid_amount ELSE 0 END) as partially_paid_amount,
               COUNT(CASE WHEN paid = 1 THEN 1 ELSE NULL END) as paid_trips,
               SUM(CASE WHEN paid = 1 THEN total_payment ELSE 0 END) as paid_amount,
               COUNT(id) as total_trips,
               SUM(total_payment) as total_amount
        FROM trips
        """)
        
        total_stats = cursor.fetchone()
        
        # Формируем сообщение с отчетом
        text = "📊 Детальный отчет по рейсам:\n\n"
        
        # Общая статистика
        unpaid_trips, unpaid_amount, partially_paid_amount, paid_trips, paid_amount, total_trips, total_amount = total_stats
        
        if unpaid_amount is None:
            unpaid_amount = 0
        if partially_paid_amount is None:
            partially_paid_amount = 0
        if paid_amount is None:
            paid_amount = 0
        if total_amount is None:
            total_amount = 0
        
        text += (
            "📈 Общая статистика:\n"
            f"• Всего рейсов: {total_trips}\n"
            f"• Неоплаченных: {unpaid_trips} (долг: {int(unpaid_amount)} ₽)\n"
            f"• Частично оплачено: {int(partially_paid_amount)} ₽\n"
            f"• Полностью оплаченных: {paid_trips} ({int(paid_amount)} ₽)\n"
            f"• Общая сумма: {int(total_amount)} ₽\n\n"
        )
        
        # Статистика по водителям
        text += "👤 Статистика по водителям:\n\n"
        
        for driver, unp_trips, unp_amount, part_paid, p_trips, p_amount, t_trips, t_amount in driver_stats:
            if unp_amount is None:
                unp_amount = 0
            if part_paid is None:
                part_paid = 0
            if p_amount is None:
                p_amount = 0
            if t_amount is None:
                t_amount = 0
            
            if unp_trips and unp_trips > 0:
                text += (
                    f"🔹 {driver}:\n"
                    f"• Неоплачено: {unp_trips} рейсов (долг: {int(unp_amount)} ₽)\n"
                    f"• Частично оплачено: {int(part_paid)} ₽\n"
                    f"• Полностью оплачено: {p_trips or 0} рейсов ({int(p_amount)} ₽)\n"
                    f"• Всего: {t_trips} рейсов ({int(t_amount)} ₽)\n\n"
                )
        
        # Разбиваем сообщение, если оно слишком длинное
        if len(text) > 4096:
            text = text[:4000] + "\n\n... (сообщение сокращено из-за лимитов Telegram)"
        
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
        )
        
        await bot.answer_callback_query(callback_query.id)
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=text,
            reply_markup=keyboard
        )
    
    except Exception as e:
        logging.error(f"Ошибка при формировании детального отчета: {str(e)}")
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.message.chat.id,
            f"❌ Ошибка при формировании отчета: {str(e)}"
        )
    
    finally:
        conn.close()

# Обработчик для ручного ввода ID рейса для оплаты
@dp.message_handler(lambda message: message.text == "✅ Отметить рейс оплаченным")
async def mark_trip_paid_cmd(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=1):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    await message.answer("Введите ID рейса, который нужно отметить как оплаченный:")
    await PaymentStates.waiting_for_trip_id.set()
    
    conn.close()

# Обработчик ввода ID рейса
@dp.message_handler(state=PaymentStates.waiting_for_trip_id)
async def process_trip_id(message: types.Message, state: FSMContext):
    try:
        trip_id = int(message.text.strip())
    except ValueError:
        await message.answer("Некорректный ID рейса. Пожалуйста, введите число.")
        return
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    # Проверяем существование рейса
    cursor.execute("""
    SELECT t.id, d.name, t.loading_city, t.unloading_city, t.total_payment, t.paid
    FROM trips t
    JOIN drivers d ON t.driver_id = d.id
    WHERE t.id = ?
    """, (trip_id,))
    
    trip = cursor.fetchone()
    
    if not trip:
        await message.answer(f"Рейс с ID {trip_id} не найден.")
        await state.finish()
        conn.close()
        return
    
    _, driver_name, load_city, unload_city, payment, paid = trip
    
    if paid == 1:
        await message.answer(f"Рейс #{trip_id} уже отмечен как оплаченный.")
        await state.finish()
        conn.close()
        return
    
    # Отмечаем рейс как оплаченный
    cursor.execute("UPDATE trips SET paid = 1 WHERE id = ?", (trip_id,))
    
    # Логируем действие
    cursor.execute(
        "INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)",
        (
            message.from_user.id,
            "Отметка рейса как оплаченного",
            f"Рейс #{trip_id}: {driver_name}, {load_city}-{unload_city}, {payment} руб."
        )
    )
    
    conn.commit()
    conn.close()
    
    await message.answer(
        f"✅ Рейс #{trip_id} отмечен как оплаченный!\n\n"
        f"👤 Водитель: {driver_name}\n"
        f"🚚 Маршрут: {load_city} → {unload_city}\n"
        f"💵 Сумма: {int(payment)} руб."
    )
    
    await state.finish()
