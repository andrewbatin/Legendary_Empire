"""
Legendary Empire ⚔️ - Telegram Game Bot
Полнофункциональный чат-бот для игры в строительство замков
Версия: 1.0
"""

import logging
import os
import json
import random
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from pathlib import Path

from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMember, ChatMemberStatus
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from telegram.error import TelegramError

# ============= КОНФИГУРАЦИЯ =============

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1001234567890"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "Yegorian_the_first")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./legendary_empire.db")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
(
    AWAITING_SUBSCRIPTION,
    AWAITING_NICKNAME,
    IN_GAME,
    ADMIN_MENU,
    ADMIN_USERS
) = range(5)

# ============= БАЗА ДАННЫХ =============

class Database:
    """Управление базой данных SQLite"""
    
    def __init__(self, db_path: str = "legendary_empire.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Инициализация БД и создание таблиц"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id BIGINT UNIQUE,
                username VARCHAR,
                game_id VARCHAR UNIQUE,
                nickname VARCHAR,
                registration_date TIMESTAMP,
                last_active TIMESTAMP,
                is_subscribed BOOLEAN DEFAULT 0,
                game_state VARCHAR DEFAULT 'IDLE',
                castle_built BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица ресурсов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INT UNIQUE,
                stones INT DEFAULT 20,
                coins INT DEFAULT 50,
                wood INT DEFAULT 20,
                diamonds INT DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        
        # Таблица игровых карт
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_maps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INT,
                map_data TEXT,
                visited_cells TEXT DEFAULT '[]',
                started_at TIMESTAMP,
                ended_at TIMESTAMP,
                is_won BOOLEAN DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ БД инициализирована")
    
    def get_connection(self):
        """Получить соединение с БД"""
        return sqlite3.connect(self.db_path)
    
    def add_user(self, telegram_id: int, username: str, nickname: str, game_id: str) -> int:
        """Добавить нового пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO users 
                (telegram_id, username, nickname, game_id, registration_date, last_active, is_subscribed, game_state)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (telegram_id, username, nickname, game_id, datetime.now(), datetime.now(), 1, 'REGISTERED'))
            
            conn.commit()
            user_id = cursor.lastrowid
            
            # Добавить ресурсы
            cursor.execute('''
                INSERT INTO resources (user_id, stones, coins, wood, diamonds)
                VALUES (?, 20, 50, 20, 1)
            ''', (user_id,))
            
            conn.commit()
            logger.info(f"✅ Пользователь {nickname} (#{game_id}) добавлен")
            return user_id
        except sqlite3.IntegrityError:
            logger.error(f"❌ Пользователь {telegram_id} уже существует")
            return -1
        finally:
            conn.close()
    
    def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Получить пользователя по Telegram ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'id': row[0],
                'telegram_id': row[1],
                'username': row[2],
                'game_id': row[3],
                'nickname': row[4],
                'registration_date': row[5],
                'last_active': row[6],
                'is_subscribed': row[7],
                'game_state': row[8],
                'castle_built': row[9]
            }
        return None
    
    def get_next_game_id(self) -> str:
        """Получить следующий ID игрока"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        count = cursor.fetchone()[0]
        conn.close()
        
        return f"#{count + 1:05d}"
    
    def get_total_users(self) -> int:
        """Получить количество всех пользователей"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        count = cursor.fetchone()[0]
        conn.close()
        
        return count
    
    def get_active_today(self) -> int:
        """Получить количество активных пользователей за день"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        one_day_ago = datetime.now() - timedelta(days=1)
        cursor.execute(
            'SELECT COUNT(*) FROM users WHERE last_active > ?',
            (one_day_ago,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        
        return count
    
    def update_game_state(self, telegram_id: int, state: str):
        """Обновить состояние игры"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'UPDATE users SET game_state = ?, last_active = ? WHERE telegram_id = ?',
            (state, datetime.now(), telegram_id)
        )
        
        conn.commit()
        conn.close()
    
    def save_map(self, user_id: int, map_data: List[List[str]]):
        """Сохранить карту"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        map_json = json.dumps(map_data)
        cursor.execute(
            'INSERT INTO game_maps (user_id, map_data, started_at) VALUES (?, ?, ?)',
            (user_id, map_json, datetime.now())
        )
        
        conn.commit()
        conn.close()
    
    def get_map(self, user_id: int) -> Optional[List[List[str]]]:
        """Получить карту"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT map_data FROM game_maps WHERE user_id = ? ORDER BY started_at DESC LIMIT 1',
            (user_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return json.loads(row[0])
        return None
    
    def export_db(self, filename: str = None) -> str:
        """Экспортировать БД в JSON"""
        if not filename:
            filename = f"legendary_empire_db_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users')
        users = cursor.fetchall()
        
        cursor.execute('SELECT * FROM resources')
        resources = cursor.fetchall()
        
        cursor.execute('SELECT * FROM game_maps')
        maps = cursor.fetchall()
        
        conn.close()
        
        export_data = {
            'exported_at': datetime.now().isoformat(),
            'users_count': len(users),
            'resources_count': len(resources),
            'maps_count': len(maps),
            'data': {
                'users': users,
                'resources': resources,
                'maps': maps
            }
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ БД экспортирована в {filename}")
        return filename

# ============= ИНИЦИАЛИЗАЦИЯ БД =============

db = Database("legendary_empire.db")

# ============= УТИЛИТЫ =============

def validate_nickname(nickname: str) -> Tuple[bool, str]:
    """Проверить корректность имени"""
    if len(nickname) < 2:
        return False, "❌ Имя должно быть минимум 2 символа"
    if len(nickname) > 15:
        return False, "❌ Имя должно быть максимум 15 символов"
    return True, ""

def generate_map() -> List[List[str]]:
    """Генерировать 10x10 карту"""
    terrains = ['🌳', '🏜️', '🏔️', '🌋', '🌊', '🌱']
    map_data = [[None for _ in range(10)] for _ in range(10)]
    
    # Разместить минимум 1 каждого типа
    used_positions = set()
    for terrain in terrains:
        while True:
            row, col = random.randint(0, 9), random.randint(0, 9)
            if (row, col) not in used_positions:
                map_data[row][col] = terrain
                used_positions.add((row, col))
                break
    
    # Заполнить остальные случайно
    for row in range(10):
        for col in range(10):
            if map_data[row][col] is None:
                map_data[row][col] = random.choice(terrains)
    
    return map_data

def format_map_buttons(user_map: List[List[str]]) -> InlineKeyboardMarkup:
    """Форматировать карту в кнопки"""
    buttons = []
    
    for row in range(10):
        row_buttons = []
        for col in range(10):
            terrain = user_map[row][col]
            button = InlineKeyboardButton(
                text=terrain,
                callback_data=f"cell_{row}_{col}"
            )
            row_buttons.append(button)
        buttons.append(row_buttons)
    
    return InlineKeyboardMarkup(buttons)

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверить подписку на канал"""
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in [
            ChatMemberStatus.CREATOR,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.MEMBER
        ]
    except TelegramError as e:
        logger.warning(f"⚠️ Ошибка проверки подписки: {e}")
        return False

# ============= ОБРАБОТЧИКИ =============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик /start"""
    user_id = update.effective_user.id
    
    # Проверить существующего пользователя
    existing_user = db.get_user(user_id)
    if existing_user and existing_user['game_state'] == 'REGISTERED':
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Далее ▶️", callback_data="continue_game")]
        ])
        await update.message.reply_text(
            f"👋 С возвращением, {existing_user['nickname']}! ({existing_user['game_id']})",
            reply_markup=keyboard
        )
        return IN_GAME
    
    # Новый пользователь - запросить подписку
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Подтвердить ✅", callback_data="check_subscription")]
    ])
    
    await update.message.reply_text(
        "Подпишитесь на официальный канал бота (ссылка на канал)\n"
        "https://t.me/+TCIZb5BW1wMzMDMy для начала.",
        reply_markup=keyboard
    )
    
    return AWAITING_SUBSCRIPTION

async def handle_subscription_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверка подписки"""
    user_id = update.effective_user.id
    query = update.callback_query
    
    await query.answer()
    
    is_subscribed = await check_subscription(user_id, context)
    
    if not is_subscribed:
        await query.edit_message_text("Ты не пройдёшь!☝️")
        return AWAITING_SUBSCRIPTION
    
    # Пользователь подписан
    await query.edit_message_text(
        "Приветствую! 👋🏻\n"
        "Для того, чтобы начать прохождение введите свое игровое имя ✍🏻"
    )
    
    return AWAITING_NICKNAME

async def handle_nickname_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода имени"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "unknown"
    nickname = update.message.text.strip()
    
    # Валидация
    is_valid, error_msg = validate_nickname(nickname)
    
    if not is_valid:
        await update.message.reply_text(f"{error_msg}\n\nПожалуйста, введите имя (2-15 символов):")
        return AWAITING_NICKNAME
    
    # Проверить существование
    existing = db.get_user(user_id)
    if existing:
        await update.message.reply_text("❌ Вы уже зарегистрированы!")
        return IN_GAME
    
    # Создать пользователя
    game_id = db.get_next_game_id()
    user_db_id = db.add_user(user_id, username, nickname, game_id)
    
    if user_db_id == -1:
        await update.message.reply_text("❌ Ошибка регистрации. Попробуйте еще раз.")
        return AWAITING_NICKNAME
    
    # Сохранить info в context
    context.user_data['user_db_id'] = user_db_id
    context.user_data['nickname'] = nickname
    context.user_data['game_id'] = game_id
    
    # Регистрационное сообщение
    message = (
        f"Успешно! ✨\n\n"
        f"Ваше имя: {nickname}\n"
        f"Ваш номер: {game_id}\n\n"
        f"Стартовый набор ресурсов:\n"
        f"20 камней 🪨\n"
        f"50 монет 💰\n"
        f"20 деревьев 🪵\n"
        f"1 алмаз 💎"
    )
    
    # Кнопки
    buttons = [[InlineKeyboardButton("Далее ▶️", callback_data="continue_game")]]
    
    # Добавить админ-панель если админ
    if update.effective_user.username == ADMIN_USERNAME:
        buttons.append([InlineKeyboardButton("Админ-панель 💻", callback_data="admin_menu")])
    
    keyboard = InlineKeyboardMarkup(buttons)
    
    await update.message.reply_text(message, reply_markup=keyboard)
    
    db.update_game_state(user_id, 'REGISTERED')
    
    return AWAITING_NICKNAME

async def continue_to_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Переход в игру"""
    user_id = update.effective_user.id
    query = update.callback_query
    
    await query.answer()
    
    # Получить пользователя
    user = db.get_user(user_id)
    if not user:
        await query.edit_message_text("❌ Ошибка: пользователь не найден")
        return AWAITING_NICKNAME
    
    # Генерировать карту
    game_map = generate_map()
    db.save_map(user['id'], game_map)
    
    db.update_game_state(user_id, 'IN_GAME')
    
    # Отправить карту
    await query.edit_message_text(
        "Это карта 🗺️\n"
        "Нажмите на клетку, и откроется локальная карта. "
        "На ней вы должны построить свой замок 🏰",
        reply_markup=format_map_buttons(game_map)
    )
    
    context.user_data['game_map'] = game_map
    
    return IN_GAME

async def handle_cell_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка клика по клетке"""
    user_id = update.effective_user.id
    query = update.callback_query
    
    await query.answer()
    
    # Парсить координаты
    parts = query.data.split("_")
    if len(parts) != 3:
        return IN_GAME
    
    row, col = int(parts[1]), int(parts[2])
    
    # Получить карту из context
    if 'game_map' not in context.user_data:
        user = db.get_user(user_id)
        context.user_data['game_map'] = db.get_map(user['id'])
    
    game_map = context.user_data['game_map']
    terrain = game_map[row][col]
    
    # Ответы
    responses = {
        '🌳': {
            'message': (
                "🏰 Поздравляю 🥳!\n"
                "Вы построили замок 🏰, не искупаысь в лаве 🌋, "
                "не умерев от кактуса 🌵, не упав с горы 🏔️, "
                "не потонув в луже 🌊, не став обедом у ростка 🌱 размером 1 мм!"
            ),
            'is_win': True,
            'new_emoji': '🏰'
        },
        '🌋': {
            'message': "☠️ Вы поплавали в лаве 🌋",
            'is_win': False
        },
        '🏜️': {
            'message': (
                "💀 Вы умерли от страшной раны, которую можно разглядеть "
                "только через супер-микроскоп. Эту рану вам нанёс кактус 🌵"
            ),
            'is_win': False
        },
        '🏔️': {
            'message': "🪨 Кажется вы полетали с вершины горы...",
            'is_win': False
        },
        '🌱': {
            'message': "🌱 Вас съел росток размером в 1 мм",
            'is_win': False
        },
        '🌊': {
            'message': "🌊 Вы затонули в луже",
            'is_win': False
        }
    }
    
    response = responses.get(terrain, {'message': 'Unknown', 'is_win': False})
    
    if response['is_win']:
        game_map[row][col] = response['new_emoji']
        db.update_game_state(user_id, 'WON')
        await query.edit_message_text(response['message'])
        return IN_GAME
    else:
        await query.edit_message_text(
            response['message'] + "\n\n✨ Попробуйте еще раз:",
            reply_markup=format_map_buttons(game_map)
        )
        return IN_GAME

# ============= АДМИН-ПАНЕЛЬ =============

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Главное меню админа"""
    query = update.callback_query
    
    await query.answer()
    
    if update.effective_user.username != ADMIN_USERNAME:
        await query.edit_message_text("❌ Недостаточно прав!")
        return IN_GAME
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Скачать БД 📥", callback_data="download_db")],
        [InlineKeyboardButton("Пользователи 👤", callback_data="admin_users")],
        [InlineKeyboardButton("Назад ◀️", callback_data="back_to_game")]
    ])
    
    await query.edit_message_text(
        "Панель Администратора 💻",
        reply_markup=keyboard
    )
    
    return ADMIN_MENU

async def admin_download_db(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Скачивание БД"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if update.effective_user.username != ADMIN_USERNAME:
        await query.answer("❌ Недостаточно прав!", show_alert=True)
        return ADMIN_MENU
    
    await query.answer()
    
    # Экспортировать БД
    filename = db.export_db()
    
    try:
        with open(filename, 'rb') as f:
            await context.bot.send_document(
                chat_id=user_id,
                document=f,
                filename=filename
            )
        
        await query.edit_message_text("✅ БД скачана!")
    except Exception as e:
        logger.error(f"❌ Ошибка при скачивании БД: {e}")
        await query.edit_message_text(f"❌ Ошибка: {e}")
    finally:
        if os.path.exists(filename):
            os.remove(filename)
    
    return ADMIN_MENU

async def admin_users_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Статистика пользователей"""
    query = update.callback_query
    
    await query.answer()
    
    total_users = db.get_total_users()
    active_today = db.get_active_today()
    
    message = (
        f"Всего игроков: {total_users}👤\n"
        f"Активных сегодня: {active_today}👨‍💻"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Назад ◀️", callback_data="admin_menu")]
    ])
    
    await query.edit_message_text(message, reply_markup=keyboard)
    
    return ADMIN_USERS

async def back_to_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Возврат в игру"""
    user_id = update.effective_user.id
    query = update.callback_query
    
    await query.answer()
    
    user = db.get_user(user_id)
    if not user:
        await query.edit_message_text("❌ Ошибка")
        return IN_GAME
    
    if 'game_map' not in context.user_data:
        context.user_data['game_map'] = db.get_map(user['id'])
    
    game_map = context.user_data['game_map']
    
    await query.edit_message_text(
        "Это карта 🗺️\n"
        "Нажмите на клетку для продолжения:",
        reply_markup=format_map_buttons(game_map)
    )
    
    return IN_GAME

# ============= ОБРАБОТЧИК ОШИБОК =============

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирование ошибок"""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

# ============= MAIN =============

def main():
    """Запуск бота"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            AWAITING_SUBSCRIPTION: [
                CallbackQueryHandler(handle_subscription_check, pattern="check_subscription")
            ],
            AWAITING_NICKNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_nickname_input),
                CallbackQueryHandler(continue_to_game, pattern="continue_game"),
                CallbackQueryHandler(admin_menu, pattern="admin_menu"),
            ],
            IN_GAME: [
                CallbackQueryHandler(handle_cell_click, pattern="^cell_"),
                CallbackQueryHandler(continue_to_game, pattern="continue_game"),
                CallbackQueryHandler(admin_menu, pattern="admin_menu"),
                CallbackQueryHandler(back_to_game, pattern="back_to_game"),
            ],
            ADMIN_MENU: [
                CallbackQueryHandler(admin_download_db, pattern="download_db"),
                CallbackQueryHandler(admin_users_stats, pattern="admin_users"),
                CallbackQueryHandler(back_to_game, pattern="back_to_game"),
            ],
            ADMIN_USERS: [
                CallbackQueryHandler(admin_menu, pattern="admin_menu"),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    
    logger.info("🚀 Legendary Empire Bot запущен!")
    application.run_polling()

if __name__ == "__main__":
    main()