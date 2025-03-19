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

# Обработчик для показа актуальных данных о задолженностях
@dp.message_handler(lambda message: message.text == "📊 Актуальные данные")
async def show_current_data(message: types.Message):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    if not await check_user_access(cursor, message.from_user.id, required_role=2):
        await message.answer("У вас нет доступа к этой функции.")
        conn.close()
        return
    
    # Создаем клавиатуру для выбора типа отчета
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("💰 Задолженности по зарплате", callback_data="salary_debt"),
        InlineKeyboardButton("📈 Статистика за месяц", callback_data="monthly_stats"),
        InlineKeyboardButton("🚚 Статистика по автопоездам", callback_data="vehicle_stats")
    )
    
    await message.answer("Выберите тип данных для просмотра:", reply_markup=keyboard)
    conn.close()

# Обработчик для показа задолженностей по зарплате
@dp.callback_query_handler(lambda c: c.data == "salary_debt")
async def show_salary_debt(callback_query: types.CallbackQuery):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Получаем сумму заработанных денег по каждому водителю 
        # (суммируем total_payment из trips)
        cursor.execute("""
        SELECT d.id, d.name, SUM(t.total_payment) as earned
        FROM drivers d
        LEFT JOIN trips t ON d.id = t.driver_id
        GROUP BY d.id
        ORDER BY d.name
        """)
        
        driver_earnings = cursor.fetchall()
        
        if not driver_earnings:
            await bot.answer_callback_query(callback_query.id)
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id, 
                message_id=callback_query.message.message_id,
                text="Нет данных о водителях или рейсах."
            )
            conn.close()
            return
        
        # Формируем сообщение с задолженностями
        text = "💵 Задолженности по зарплате:\n\n"
        
        for driver_id, name, earned in driver_earnings:
            if earned is None:
                earned = 0
            
            # Здесь можно добавить логику учета выплат, если они есть в БД
            # Пока считаем, что все заработанное - это долг
            debt = earned
            
            if debt > 0:
                text += f"👤 {name}: {int(debt)} руб.\n"
            else:
                text += f"👤 {name}: нет задолженности\n"
        
        # Добавляем общую сумму
        total_debt = sum(earned if earned else 0 for _, _, earned in driver_earnings)
        text += f"\n💰 Общая задолженность: {int(total_debt)} руб."
        
        # Клавиатура для доп. действий
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("📋 Экспорт в CSV", callback_data="export_debt"),
            InlineKeyboardButton("🔍 Подробный отчет", callback_data="detailed_debt"),
            InlineKeyboardButton("◀️ Назад", callback_data="back_to_current_data")
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

# Обработчик для экспорта данных о задолженностях в CSV
@dp.callback_query_handler(lambda c: c.data == "export_debt")
async def export_debt(callback_query: types.CallbackQuery):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Получаем данные о заработках водителей
        cursor.execute("""
        SELECT d.id, d.name, 
               SUM(t.total_payment) as earned,
               COUNT(t.id) as trips_count,
               SUM(t.distance) as total_distance
        FROM drivers d
        LEFT JOIN trips t ON d.id = t.driver_id
        GROUP BY d.id
        ORDER BY d.name
        """)
        
        driver_data = cursor.fetchall()
        
        if not driver_data:
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
            "ID", "Водитель", "Заработано (руб.)", "Количество рейсов", 
            "Общий пробег (км)", "Задолженность (руб.)"
        ])
        
        # Данные
        for driver_id, name, earned, trips_count, distance in driver_data:
            if earned is None:
                earned = 0
            if trips_count is None:
                trips_count = 0
            if distance is None:
                distance = 0
            
            # Задолженность (пока просто равна earned, можно изменить логику)
            debt = earned
            
            writer.writerow([
                driver_id, name, earned, trips_count, distance, debt
            ])
        
        # Конвертируем в байты
        csv_bytes = output.getvalue().encode('utf-8-sig')
        
        # Отправляем файл
        filename = f"salary_debt_{datetime.now().strftime('%Y-%m-%d')}.csv"
        
        await bot.answer_callback_query(callback_query.id)
        await bot.send_document(
            callback_query.message.chat.id,
            (filename, io.BytesIO(csv_bytes)),
            caption="Отчет по задолженностям"
        )
    
    except Exception as e:
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.message.chat.id,
            f"Ошибка при экспорте: {str(e)}"
        )
    
    finally:
        conn.close()

# Обработчик для подробного отчета о задолженностях
@dp.callback_query_handler(lambda c: c.data == "detailed_debt")
async def detailed_debt(callback_query: types.CallbackQuery):
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Получаем список водителей
        cursor.execute("SELECT id, name FROM drivers ORDER BY name")
        drivers = cursor.fetchall()
        
        if not drivers:
            await bot.answer_callback_query(callback_query.id)
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text="Нет данных о водителях."
            )
            conn.close()
            return
        
        # Создаем клавиатуру для выбора водителя
        keyboard = InlineKeyboardMarkup(row_width=1)
        for driver_id, name in drivers:
            keyboard.add(InlineKeyboardButton(
                f"👤 {name}", callback_data=f"driver_debt_{driver_id}"
            ))
        
        keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data="salary_debt"))
        
        await bot.answer_callback_query(callback_query.id)
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="Выберите водителя для просмотра подробного отчета:",
            reply_markup=keyboard
        )
    
    except Exception as e:
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.message.chat.id,
            f"Ошибка при получении списка водителей: {str(e)}"
        )
    
    finally:
        conn.close()

# Обработчик для детального отчета по конкретному водителю
@dp.callback_query_handler(lambda c: c.data.startswith('driver_debt_'))
async def driver_debt_details(callback_query: types.CallbackQuery):
    driver_id = int(callback_query.data.split('_')[2])
    
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    
    try:
        # Получаем данные о водителе
        cursor.execute("""
        SELECT name, km_rate, side_loading_rate, roof_loading_rate,
               regular_downtime_rate, forced_downtime_rate
        FROM drivers
        WHERE id = ?
        """, (driver_id,))
        
        driver_data = cursor.fetchone()
        
        if not driver_data:
            await bot.answer_callback_query(callback_query.id)
            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text="Водитель не найден."
            )
            conn.close()
            return
        
        name, km_rate, side_rate, roof_rate, reg_rate, forced_rate = driver_data
        
        # Получаем рейсы водителя за последние 30 дней
        cursor.execute("""
        SELECT id, loading_city, unloading_city, distance, total_payment, created_at
        FROM trips
        WHERE driver_id = ? AND created_at >= datetime('now', '-30 days')
        ORDER BY created_at DESC
        """, (driver_id,))
        
        recent_trips = cursor.fetchall()
        
        # Получаем общую сумму заработка
        cursor.execute("""
        SELECT SUM(total_payment)
        FROM trips
        WHERE driver_id = ?
        """, (driver_id,))
        
        total_earned = cursor.fetchone()[0] or 0
        
        # Формируем сообщение
        text = f"📊 Отчет по водителю: {name}\n\n"
        text += f"💰 Общая задолженность: {int(total_earned)} руб.\n\n"
        
        text += "📋 Ставки:\n"
        text += f"• Километр: {km_rate} руб.\n"
        text += f"• Боковой тент: {side_rate} руб.\n"
        text += f"• Крыша: {roof_rate} руб.\n"
        text += f"• Обычный простой: {reg_rate} руб/день\n"
        text += f"• Вынужденный простой: {forced_rate} руб/день\n\n"
        
        if recent_trips:
            text += "🗂️ Последние рейсы (30 дней):\n"
            for trip_id, load, unload, distance, payment, date in recent_trips[:5]:  # Ограничиваем до 5 рейсов
                date_str = date.split(" ")[0]
                text += f"• #{trip_id} ({date_str}): {load}-{unload}, {int(payment)} руб.\n"
            
            if len(recent_trips) > 5:
                text += f"...и еще {len(recent_trips) - 5} рейсов\n"
        else:
            text += "За последние 30 дней рейсов не было\n"
        
        # Клавиатура для возврата
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("◀️ Назад к списку", callback_data="detailed_debt"))
        
        await bot.answer_callback_query(callback_query.id)
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=text,
            reply_markup=keyboard
        )
    
    except Exception as e:
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(
            callback_query.message.chat.id,
            f"Ошибка при получении данных: {str(e)}"
        )
    
    finally:
        conn.close()

# Обработчик для возврата к выбору типа данных
@dp.callback_query_handler(lambda c: c.data == "back_to_current_data")
async def back_to_current_data(callback_query: types.CallbackQuery):
    # Создаем клавиатуру для выбора типа отчета
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("💰 Задолженности по зарплате", callback_data="salary_debt"),
        InlineKeyboardButton("📈 Статистика за месяц", callback_data="monthly_stats"),
        InlineKeyboardButton("🚚 Статистика по автопоездам", callback_data="vehicle_stats")
    )
    
    await bot.answer_callback_query(callback_query.id)
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Выберите тип данных для просмотра:",
        reply_markup=keyboard
    )

# Заглушки для остальных отчетов
@dp.callback_query_handler(lambda c: c.data == "monthly_stats")
async def monthly_stats(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="📈 Статистика за месяц в разработке...",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("◀️ Назад", callback_data="back_to_current_data")
        )
    )

@dp.callback_query_handler(lambda c: c.data == "vehicle_stats")
async def vehicle_stats(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="🚚 Статистика по автопоездам в разработке...",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("◀️ Назад", callback_data="back_to_current_data")
        )
    )
