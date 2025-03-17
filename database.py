import sqlite3

def create_tables(cursor):
    # Таблица пользователей и ролей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        role INTEGER DEFAULT 2,  -- 1: Редактор, 2: Просмотрщик
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Таблица водителей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS drivers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        km_rate REAL NOT NULL,  -- Ставка за километр
        side_loading_rate REAL NOT NULL,  -- Ставка за погрузку/разгрузку бокового тента
        roof_loading_rate REAL NOT NULL,  -- Ставка за погрузку/разгрузку крыши
        regular_downtime_rate REAL NOT NULL,  -- Ставка за обычный простой
        forced_downtime_rate REAL NOT NULL,  -- Ставка за вынужденный простой
        vehicle_id INTEGER,  -- Привязка к автопоезду
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (vehicle_id) REFERENCES vehicles (id)
    )
    ''')
    
    # Таблица автопоездов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS vehicles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        truck_number TEXT NOT NULL,
        trailer_number TEXT NOT NULL,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Таблица рейсов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS trips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        driver_id INTEGER,
        vehicle_id INTEGER,
        loading_city TEXT NOT NULL,
        unloading_city TEXT NOT NULL,
        distance REAL NOT NULL,
        side_loading_count INTEGER DEFAULT 0,
        roof_loading_count INTEGER DEFAULT 0,
        total_payment REAL NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (driver_id) REFERENCES drivers (id),
        FOREIGN KEY (vehicle_id) REFERENCES vehicles (id)
    )
    ''')
    
    # Таблица простоев
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS downtimes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trip_id INTEGER,
        type INTEGER NOT NULL,  -- 1: обычный, 2: вынужденный
        hours REAL NOT NULL,
        payment REAL NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (trip_id) REFERENCES trips (id)
    )
    ''')
    
    # Таблица логов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT NOT NULL,
        details TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')

def init_db():
    conn = sqlite3.connect('salary_bot.db')
    cursor = conn.cursor()
    create_tables(cursor)
    
    # Проверяем наличие администратора
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 0")
    admin_count = cursor.fetchone()[0]
    
    if admin_count == 0:
        admin_id = 403126106  
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, role) VALUES (?, 'admin', 0)",
            (admin_id,)
        )
        print(f"Добавлен первый администратор с ID: {admin_id}")
    
    conn.commit()
    return conn
